# Copyright (c) 2019 SUSE LLC.  All rights reserved.
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
import threading
import logging

from datetime import datetime
from pytz import utc
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import (
    EVENT_JOB_MAX_INSTANCES,
    EVENT_JOB_SUBMITTED
)

from obs_img_utils.api import OBSImageUtil

# project
from mash.services.obs.defaults import Defaults
from mash.log.filter import SchedulerLoggingFilter
from mash.services.status_levels import FAILED, SUCCESS


class OBSImageBuildResult(object):
    """
    Implements Open BuildService image result watchdog

    Attributes

    * :attr:`job_id`
      job id number

    * :attr:`job_file`
      job file containing the job description

    * :attr:`download_url`
      Buildservice URL

    * :attr:`image_name`
      Image name as specified in the KIWI XML description of the
      Buildservice project and package

    * :attr:`last_service`
      The last service for the job.

    * :attr:`conditions`
      Criteria for the image build which is a list of hashes like
      the following example demonstrates:

      conditions=[
          # a package condition with version and release spec
          {
           'package_name': 'kernel-default',
           'version': '4.13.1',
           'build_id': '1.1'
          },
          # a image version condition
          {'image': '1.42.1'}
      ]

    * :attr:`arch`
      Buildservice package architecture, defaults to: x86_64

    * :attr:`download_directory`
      Download directory name, defaults to: /tmp

    * :attr:`notification_email`
      Email to send job notifications.

    * :attr:`notification_type`
      The frequency of notification emails.

    * :attr:`profile`
      The multibuild profile name for the image.
    """
    def __init__(
        self, job_id, job_file, download_url, image_name, last_service,
        log_callback, conditions=None, arch='x86_64',
        download_directory=Defaults.get_download_dir(),
        notification_email=None, notification_type='single',
        profile=None
    ):
        self.arch = arch
        self.job_id = job_id
        self.job_file = job_file
        self.download_directory = os.path.join(download_directory, job_id)
        self.download_url = download_url
        self.image_name = image_name
        self.last_service = last_service
        self.image_metadata_name = None
        self.conditions = conditions
        self.scheduler = None
        self.job = None
        self.job_deleted = False
        self.job_nonstop = False
        self.log_callback = None
        self.result_callback = None
        self.notification_callback = None
        self.iteration_count = 0
        self.notification_email = notification_email
        self.notification_type = notification_type
        self.profile = profile
        self.job_status = 'prepared'
        self.progress_log = {}
        self.log_callback = logging.LoggerAdapter(
            log_callback,
            {'job_id': self.job_id}
        )

        # How often to update log callback with download progress.
        # 25 updates every 25%. I.e. 25, 50, 75, 100.
        self.download_progress_percent = 25

        kwargs = {
            'conditions': self.conditions,
            'arch': self.arch,
            'target_directory': self.download_directory,
            'conditions_wait_time': 900,
            'log_callback': self.log_callback,
            'report_callback': self.progress_callback
        }

        if self.profile:
            kwargs['profile'] = self.profile

        self.downloader = OBSImageUtil(
            self.download_url,
            self.image_name,
            **kwargs
        )

    def start_watchdog(
        self, interval_sec=5, nonstop=False, isotime=None
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
        job_time = None

        if isotime:
            job_time = datetime.strptime(isotime[:19], '%Y-%m-%dT%H:%M:%S')

        self.scheduler = BackgroundScheduler(timezone=utc)

        if nonstop:
            self.job = self.scheduler.add_job(
                self._update_image_status, 'interval',
                max_instances=1, seconds=interval_sec,
                start_date=job_time, timezone='utc'
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
                run_date=job_time, timezone='utc'
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
            self.job_deleted = True
        except Exception:
            pass

    def set_result_handler(self, function):
        self.result_callback = function

    def set_notification_handler(self, function):
        self.notification_callback = function

    def call_result_handler(self):
        self._result_callback()

    def _result_callback(self):
        if self.result_callback:
            self.result_callback(
                self.job_id, {
                    'obs_result': {
                        'id': self.job_id,
                        'image_file':
                            self.downloader.image_status['image_source'],
                        'status': self.job_status
                    }
                }
            )

    def _notification_callback(
        self, status, error=None
    ):
        utctime = 'always' if self.job_nonstop else 'now'

        if self.notification_callback:
            self.notification_callback(
                self.job_id, self.notification_email, self.notification_type,
                status, utctime, self.last_service, self.iteration_count,
                error
            )

    def _job_submit_event(self, event):
        if self.job_nonstop:
            self.log_callback.info('Nonstop job submitted')
        else:
            self.log_callback.info('Oneshot Job submitted')

    def _job_skipped_event(self, event):
        # Job is still active while the next _update_image_status
        # event was scheduled. In this case we just skip the event
        # and keep the active job waiting for an obs change
        pass

    def _wait_for_new_image(self):
        osc_result_thread = threading.Thread(
            target=self.downloader.wait_for_new_image
        )
        osc_result_thread.start()
        osc_result_thread.join()
        self._update_image_status()

    def _update_image_status(self):
        self.iteration_count += 1

        self.log_callback.extra = {
            'job_id': self.job_id,
            'iteration': self.iteration_count
        }
        self.log_callback.info('Job running')

        try:
            image_source = self.downloader.get_image()
            self.log_callback.info(
                'Downloaded: {0}'.format(image_source)
            )

            self.job_status = 'success'
            self.log_callback.info(
                'Job status: {0}'.format(self.job_status)
            )
            self._result_callback()

            if self.job_nonstop:
                self.log_callback.info('Waiting for image update')
                self._wait_for_new_image()
            else:
                self._notification_callback(SUCCESS)
                self.log_callback.info('Job done')
        except Exception as issue:
            msg = '{0}: {1}'.format(type(issue).__name__, issue)

            self.job_status = 'failed'
            self.log_callback.error(msg)
            self._notification_callback(FAILED, msg)

            if not self.job_nonstop:
                self._result_callback()

    def progress_callback(self, block_num, read_size, total_size, done=False):
        """
        Update progress in log callback
        """
        if done:
            self.log_callback.info('Image download finished.')
        else:
            percent = int(((block_num * read_size) / total_size) * 100)

            if percent % self.download_progress_percent == 0 \
                    and percent not in self.progress_log:
                self.log_callback.info(
                    'Image {progress}% downloaded.'.format(
                        progress=str(percent)
                    )
                )
                self.progress_log[percent] = True
