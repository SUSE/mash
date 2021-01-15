# Copyright (c) 2021 SUSE LLC.  All rights reserved.
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

from azure.mgmt.compute import ComputeManagementClient

# project
from mash.services.mash_job import MashJob
from mash.mash_exceptions import MashCreateException
from mash.services.status_levels import SUCCESS
from mash.utils.azure import image_exists, delete_image, get_client_from_json


class AzureCreateJob(MashJob):
    """
    Implements Azure VM image creation.
    """
    def post_init(self):
        try:
            self.container = self.job_config['container']
            self.storage_account = self.job_config['storage_account']
            self.account = self.job_config.get('account')
            self.region = self.job_config.get('region')
            self.resource_group = self.job_config.get('resource_group')
        except KeyError as error:
            raise MashCreateException(
                'Azure create jobs require a(n) {0} '
                'key in the job doc.'.format(
                    error
                )
            )

        self.boot_firmware = self.job_config.get('boot_firmware', ['bios'])

    def run_job(self):
        self.status = SUCCESS
        self.status_msg['images'] = {}
        self.log_callback.info('Creating image.')

        self.cloud_image_name = self.status_msg['cloud_image_name']
        self.blob_name = self.status_msg['blob_name']

        self.request_credentials([self.account])
        credentials = self.credentials[self.account]

        for firmware in self.boot_firmware:
            image_name = self._create_image(
                self.blob_name,
                credentials,
                boot_firmware=firmware
            )
            self.status_msg['images'][firmware] = image_name

        self.log_callback.info(
            'Image has ID: {0} in region {1}'.format(
                self.cloud_image_name,
                self.region
            )
        )

    def _create_image(self, blob_name, credentials, boot_firmware='bios'):
        """
        Create image in ARM from existing page blob.

        If boot firmware is uefi use hyper v generation of V2.
        """
        if boot_firmware == 'uefi':
            hyper_v_generation = 'V2'
            image_name = '{name}_uefi'.format(name=self.cloud_image_name)
        else:
            hyper_v_generation = 'V1'
            image_name = self.cloud_image_name

        if image_exists(credentials, image_name):
            self.log_callback.info(
                'Deleting image: {0}, image will be replaced.'.format(
                    image_name
                )
            )
            delete_image(
                credentials,
                self.resource_group,
                image_name
            )

        compute_client = get_client_from_json(
            ComputeManagementClient,
            credentials
        )

        async_create_image = compute_client.images.begin_create_or_update(
            self.resource_group,
            image_name, {
                'location': self.region,
                'hyper_v_generation': hyper_v_generation,
                'storage_profile': {
                    'os_disk': {
                        'os_type': 'Linux',
                        'os_state': 'Generalized',
                        'caching': 'ReadWrite',
                        'blob_uri': 'https://{0}.{1}/{2}/{3}'.format(
                            self.storage_account,
                            'blob.core.windows.net',
                            self.container,
                            blob_name
                        )
                    }
                }
            }
        )
        async_create_image.result()

        return image_name
