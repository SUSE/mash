# Copyright (c) 2017 SUSE Linux GmbH.  All rights reserved.
#
# This file is part of mash.
#
# mash is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# mash is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with mash.  If not, see <http://www.gnu.org/licenses/>
#
import os
import pickle
import re
import logging
import hashlib
from distutils.dir_util import mkpath
from datetime import datetime
from pytz import utc
from tempfile import NamedTemporaryFile
from collections import namedtuple
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import (
    EVENT_JOB_MAX_INSTANCES,
    EVENT_JOB_SUBMITTED
)
from xml.etree import cElementTree as ET

# from osc project
import osc
from osc.core import (
    get_binarylist,
    get_binary_file,
    get_results,
    meta_exists,
    unlock_package,
    edit_meta
)

# project
from mash.services.obs.defaults import Defaults
from mash.logging_filter import SchedulerLoggingFilter
from mash.exceptions import (
    MashOBSLookupError,
    MashImageDownloadError,
    MashVersionExpressionError,
    MashOBSResultError,
    MashJobRetireError,
    MashError
)


class OBSImageBuildResult(object):
    """
    Implements Open BuildService image result watchdog

    Attributes

    * :attr:`job_id`
      job id number

    * :attr:`job_file`
      job file containing the job description

    * :attr:`project`
      Buildservice project path name

    * :attr:`package`
      Buildservice package name which has to be a kiwi image build

    * :attr:`conditions`
      Criteria for the image build which is a list of hashes like
      the following example demonstrates:

      conditions=[
          # a package condition with version and release spec
          {'package': ['kernel-default', '4.13.1', '1.1']},
          # a image version condition
          {'image': '1.42.1'}
      ]

    * :attr:`arch`
      Buildservice package architecture, defaults to: x86_64

    * :attr:`api_url`
      Buildservice URL, defaults to: https://api.opensuse.org

    * :attr:`repository`
      Buildservice package repository, defaults to: images

    * :attr:`download_directory`
      Download directory name, defaults to: /tmp
    """
    def __init__(
        self, job_id, job_file, project, package, conditions=None,
        arch='x86_64', api_url='https://api.opensuse.org', repository='images',
        download_directory=Defaults.get_download_dir()
    ):
        self.job_id = job_id
        self.job_file = job_file
        self.download_directory = download_directory
        self.jobs_done_dir = Defaults.get_jobs_done_dir()
        self.api_url = api_url
        self.repository = repository
        self.arch = arch
        self.project = project
        self.package = package
        self.conditions = conditions
        self.image_status = self._init_status()
        self.scheduler = None
        self.job = None
        self.job_nonstop = False
        self.lock_set_by_this_instance = False

        try:
            osc.conf.get_config()
        except Exception as e:
            self._log_error(
                'Reading osc config failed: {0}'.format(e)
            )

    def start_watchdog(
        self, interval_sec=30, nonstop=False, isotime=None
    ):
        """
        Start a background job which triggers the update
        of the image build data and image fetched from the obs project.

        The job is started at a given data/time which must
        be the result of a isoformat() call. If no data/time is
        specified the job runs immediately. If nonstop is true
        the job runs continuously in the given interval but allows
        for one active instance only. The running job causes any
        subsequent jobs to be skipped until the state of the build
        results changes

        :param bool nonstop: run continuously
        :param string isotime: data and time by isoformat()
        :param int interval_sec: interval for nonstop jobs
        """
        self.job_nonstop = nonstop
        time = None
        if isotime:
            time = datetime.strptime(isotime[:19], '%Y-%m-%dT%H:%M:%S')
        self.scheduler = BackgroundScheduler(timezone=utc)
        if nonstop:
            self.job = self.scheduler.add_job(
                self._update_image_status, 'interval',
                max_instances=1, seconds=interval_sec,
                start_date=time, timezone='utc'
            )
            self.scheduler.add_listener(
                self._job_skipped_event, EVENT_JOB_MAX_INSTANCES
            )
            logging.getLogger("apscheduler.scheduler").addFilter(
                SchedulerLoggingFilter()
            )
        else:
            self.job = self.scheduler.add_job(
                self._update_image_status, 'date',
                run_date=time, timezone='utc'
            )
        self.scheduler.add_listener(
            self._job_submit_event, EVENT_JOB_SUBMITTED
        )
        self.scheduler.start()

    def stop_watchdog(self):
        """
        Remove active job from scheduler

        Current image status is retained
        """
        try:
            self.job.remove()
        except Exception:
            pass

    def get_image_status(self):
        """
        Return status of the image and condition states
        """
        return self.image_status

    def get_image(self):
        """
        Download image and shasum to given file

        :param string target_filename: target file name
        """
        downloaded = []
        binary_list = self._get_binary_list()
        mkpath(self.download_directory)
        for binary in binary_list:
            if self._match_image_file(binary.name):
                target_filename = os.sep.join(
                    [self.download_directory, binary.name]
                )
                try:
                    get_binary_file(
                        self.api_url, self.project, self.repository, self.arch,
                        binary.name,
                        package=self.package,
                        target_filename=target_filename,
                        target_mtime=binary.mtime
                    )
                    downloaded.append(target_filename)
                except Exception as e:
                    raise MashImageDownloadError(
                        'Job[{0}]: Download {1}:{2}/{3} failed with {4}'.format(
                            self.job_id, self.project, self.package,
                            binary.name, e
                        )
                    )
        return downloaded

    def _match_image_file(self, name):
        extensions = ['.xz', '.iso', 'xz.sha256', 'iso.sha256']
        for extension in extensions:
            if name.endswith(extension):
                return True
        return False

    def _init_status(self):
        image_status = {
            'name': self.package,
            'job_status': 'prepared',
            'image_source': 'unknown',
            'packages_checksum': 'unknown',
            'version': 'unknown',
            'conditions': [],
            'errors': []
        }
        if self.conditions:
            for condition in self.conditions:
                condition['status'] = None
            image_status['conditions'] = self.conditions
        return image_status

    def _job_submit_event(self, event):
        if not self.job_nonstop:
            self.image_status['job_status'] = 'oneshot'

    def _job_skipped_event(self, event):
        # Job is still active while the next _update_image_status
        # event was scheduled. In this case we just skip the event
        # and keep the active job waiting for an obs change
        pass

    def _lock(self):
        try:
            obs_target = (self.project, self.package)
            obs_type = 'pkg'
            meta = meta_exists(
                metatype=obs_type, path_args=obs_target,
                create_new=False, apiurl=self.api_url
            )
            root = ET.fromstring(''.join(meta))
            if not root.find('lock'):
                lock = ET.SubElement(root, 'lock')
                ET.SubElement(lock, 'enable')
                meta = ET.tostring(root)
                # JFI: edit_meta prints unwanted messages on stdout
                edit_meta(
                    metatype=obs_type, path_args=obs_target,
                    data=meta, msg='lock'
                )
                self.lock_set_by_this_instance = True
            return True
        except Exception as e:
            self._log_error(
                'Lock failed for {0}/{1}: {2}: {3}'.format(
                    self.project, self.package, type(e).__name__, e
                )
            )
            return False

    def _unlock(self):
        if self.lock_set_by_this_instance:
            try:
                unlock_package(
                    self.api_url, self.project, self.package, 'unlock'
                )
            except Exception as e:
                self._log_error(
                    'Unlock failed for {0}/{1}: {2}: {3}'.format(
                        self.project, self.package, type(e).__name__, e
                    )
                )

    def _wait_for_new_image(self):
        parameters = {
            'apiurl': self.api_url,
            'project': self.project,
            'package': self.package,
            'repository': [self.repository],
            'arch': [self.arch],
            'wait': True
        }
        try:
            # JFI: get_results prints unwanted messages on stdout
            get_results(**parameters)
        except Exception as e:
            raise MashOBSResultError(
                'Job[{0}]: Wait for new image failed {1}/{2}: {3}: {4}'.format(
                    self.job_id, self.project, self.package, type(e).__name__, e
                )
            )

    def _retire_job(self):
        try:
            # delete what we can't pickle from self.__dict__
            job_backup = self.job
            scheduler_backup = self.scheduler
            retired_job = os.sep.join(
                [self.jobs_done_dir, self.job_id + '.pickle']
            )
            os.remove(self.job_file)
            self.job_file = retired_job
            with open(retired_job, 'wb') as retired:
                self.job = None
                self.scheduler = None
                pickle.dump(self, retired)
            self.job = job_backup
            self.scheduler = scheduler_backup
        except Exception as e:
            raise MashJobRetireError(
                'Job[{0}]: Failed to retire: {1}'.format(self.job_id, e)
            )

    def _image_conditions_complied(self):
        if self.image_status['version'] == 'unknown':
            # if no image build was found, conditions no matter
            # if there are any are not complied
            return False
        for condition in self.image_status['conditions']:
            if condition['status'] is not True:
                return False
        return True

    def _log_error(self, message):
        self.image_status['errors'].append(message)
        # delete duplicate entries from error list, order is not preserved
        self.image_status['errors'] = sorted(
            list(set(self.image_status['errors']))
        )
        self.image_status['job_status'] = 'failed'

    def _update_image_status(self):
        try:
            if self.job_nonstop:
                self.image_status['errors'] = []
            if not self._lock():
                self._unlock()
                return
            self.image_status['job_status'] = 'running'
            packages = self._lookup_image_packages_metadata()
            for condition in self.image_status['conditions']:
                if 'image' in condition:
                    if self.image_status['version'] == condition['image']:
                        condition['status'] = True
                    else:
                        condition['status'] = False
                elif 'package' in condition:
                    if self._lookup_package(packages, condition['package']):
                        condition['status'] = True
                    else:
                        condition['status'] = False

            if self._image_conditions_complied():
                packages_digest = hashlib.md5()
                packages_digest.update(format(packages))
                packages_checksum = packages_digest.hexdigest()
                if packages_checksum != self.image_status['packages_checksum']:
                    self.image_status['image_source'] = 'downloading...'
                    self.image_status['packages_checksum'] = 'unknown'
                    self.image_status['image_source'] = self.get_image()
                self.image_status['packages_checksum'] = packages_checksum
                self.image_status['job_status'] = 'success'
            if self.image_status['job_status'] != 'success':
                self.image_status['job_status'] = 'failed'
            self._unlock()
            if self.job_nonstop:
                self._wait_for_new_image()
            else:
                self._retire_job()
        except MashError as e:
            self._unlock()
            self._log_error(
                '{0}: {1}'.format(type(e).__name__, e)
            )

    def _lookup_image_packages_metadata(self):
        packages_file = NamedTemporaryFile()
        for binary in self._get_binary_list():
            if binary.name.endswith('.sha256'):
                try:
                    # The .sha256 file name uses the same name format than
                    # the real image name. However the name extension of the
                    # real image differs according to the image type. Matching
                    # against the unique .sha256 file is therefore the most
                    # simple file match
                    self.image_status['version'] = binary.name.split('-')[-2]
                except Exception:
                    # naming conventions for image names in obs violated
                    # or no image exists. This will reset the image status
                    # back to unknown
                    self.image_status['version'] = 'unknown'
                    self._log_error(
                        'Unexpected image name format: {0}'.format(binary.name)
                    )
            if '.packages' in binary.name:
                get_binary_file(
                    self.api_url, self.project, self.repository, self.arch,
                    binary.name,
                    package=self.package,
                    target_filename=packages_file.name,
                    target_mtime=binary.mtime
                )
        if self.image_status['version'] == 'unknown':
            self._log_error('No image binary found')
        package_type = namedtuple(
            'package_type', [
                'version', 'release', 'arch', 'checksum'
            ]
        )
        result_packages = {}
        with open(packages_file.name) as packages:
            for package in packages.readlines():
                package_digest = hashlib.md5()
                package_digest.update(package)
                package_info = package.split('|')
                package_name = package_info[0]
                package_result = package_type(
                    version=package_info[2],
                    release=package_info[3],
                    arch=package_info[4],
                    checksum=package_digest.hexdigest()
                )
                result_packages[package_name] = package_result
        return result_packages

    def _version_compare(self, expression):
        expression = expression.replace('.', '')
        if re.match('^\d+ (<|>|<=|>=|==)\d+$', expression):
            return eval(expression)
        else:
            raise MashVersionExpressionError(
                'Job[{0}]: Invalid version compare expression: "{1}"'.format(
                    self.job_id, expression
                )
            )

    def _lookup_package(self, packages, package_search_data):
        package_name = package_search_data[0]
        if package_name not in packages:
            return False

        if len(package_search_data) > 1:
            # we want to lookup a specific version, release of the package
            package_data = packages[package_name]

            package_lookup_version = package_search_data[1]
            package_lookup_release = None
            if len(package_search_data) == 3:
                package_lookup_release = package_search_data[2]

            version_check = '{0} {1}'.format(
                package_data.version, package_lookup_version
            )
            if self._version_compare(version_check):
                if not package_lookup_release:
                    return True
                release_check = '{0} {1}'.format(
                    package_data.release, package_lookup_release
                )
                if self._version_compare(release_check):
                    return True
            return False
        else:
            # we want to lookup just the package name
            return True

    def _get_binary_list(self):
        try:
            return get_binarylist(
                self.api_url, self.project, self.repository, self.arch,
                self.package, verbose=True
            )
        except Exception as e:
            raise MashOBSLookupError(
                'Job[{0}]: {1}/{2} said {3}'.format(
                    self.job_id, self.project, self.package, e
                )
            )
