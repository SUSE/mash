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
import random
import traceback

from mash.mash_exceptions import MashTestException
from mash.services.mash_job import MashJob
from mash.services.status_levels import EXCEPTION, SUCCESS
from mash.services.test.utils import process_test_result
from mash.utils.azure import delete_image, delete_blob
from mash.utils.mash_utils import create_ssh_key_pair, create_json_file
from mash.services.test.img_proof_helper import img_proof_test

instance_types = [
    'Standard_B1s',
    'Standard_D2_v3',
    'Standard_E2_v3',
    'Standard_F2s_v2'
]


class AzureTestJob(MashJob):
    """
    Class for an Azure test job.
    """

    def post_init(self):
        """
        Post initialization method.
        """
        try:
            self.account = self.job_config['account']
            self.region = self.job_config['region']
            self.container = self.job_config['container']
            self.resource_group = self.job_config['resource_group']
            self.storage_account = self.job_config['storage_account']
            self.tests = self.job_config['tests']
        except KeyError as error:
            raise MashTestException(
                'Azure test jobs require a(n) {0} '
                'key in the job doc.'.format(
                    error
                )
            )

        self.description = self.job_config.get('description')
        self.distro = self.job_config.get('distro', 'sles')
        self.instance_type = self.job_config.get('instance_type')
        self.ssh_user = self.job_config.get('ssh_user', 'azureuser')
        self.cleanup_images = self.job_config.get('cleanup_images')

        if not self.instance_type:
            self.instance_type = random.choice(instance_types)

        self.ssh_private_key_file = self.config.get_ssh_private_key_file()
        self.img_proof_timeout = self.config.get_img_proof_timeout()

        if not os.path.exists(self.ssh_private_key_file):
            create_ssh_key_pair(self.ssh_private_key_file)

    def run_job(self):
        """
        Tests image with img-proof and update status and results.
        """
        self.status = SUCCESS
        self.log_callback.info(
            'Running img-proof tests against image with '
            'type: {inst_type}.'.format(
                inst_type=self.instance_type
            )
        )

        self.request_credentials([self.account])
        credentials = self.credentials[self.account]
        self.cloud_image_name = self.status_msg['cloud_image_name']

        with create_json_file(credentials) as auth_file:
            for firmware, image in self.status_msg['images'].items():
                try:
                    result = img_proof_test(
                        cloud=self.cloud,
                        description=self.description,
                        distro=self.distro,
                        image_id=image,
                        instance_type=self.instance_type,
                        img_proof_timeout=self.img_proof_timeout,
                        region=self.region,
                        service_account_file=auth_file,
                        ssh_private_key_file=self.ssh_private_key_file,
                        ssh_user=self.ssh_user,
                        tests=self.tests,
                        log_callback=self.log_callback,
                        boot_firmware=firmware
                    )
                except Exception as error:
                    self.add_error_msg(str(error))
                    result = {
                        'status': EXCEPTION,
                        'msg': str(traceback.format_exc())
                    }

                self.status = process_test_result(
                    result,
                    self.log_callback,
                    self.region,
                    self.status_msg
                )

                if self.status != SUCCESS:
                    break

        if self.cleanup_images or \
                (self.status != SUCCESS and self.cleanup_images is not False):
            self.cleanup_all_images()

    def cleanup_all_images(self):
        credentials = self.credentials[self.account]
        blob_name = self.status_msg['blob_name']

        for firmware, image in self.status_msg['images'].items():
            self.log_callback.info(
                'Cleaning up image: {0} in region: {1}.'.format(
                    image,
                    self.region
                )
            )

            try:
                delete_image(
                    credentials,
                    self.resource_group,
                    image
                )
            except Exception as error:
                msg = 'Failed to cleanup image: {0}'.format(error)
                self.log_callback.warning(msg)
                self.add_error_msg(msg)

        try:
            delete_blob(
                credentials,
                blob_name,
                self.container,
                self.resource_group,
                self.storage_account
            )
        except Exception as error:
            msg = 'Failed to cleanup image page blob: {0}'.format(error)
            self.log_callback.warning(msg)
            self.add_error_msg(msg)
