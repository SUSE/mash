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

from mash.mash_exceptions import MashJobCreatorException
from mash.services.jobcreator.base_job import BaseJob
from mash.utils.json_format import JsonFormat


class AzureJob(BaseJob):
    """
    Azure job message class.
    """

    def post_init(self):
        """
        Post initialization method.
        """
        try:
            self.cloud_account = self.kwargs['cloud_account']
        except KeyError as error:
            raise MashJobCreatorException(
                'Azure jobs require a(n) {0} key in the job doc.'.format(
                    error
                )
            )

        self.vm_images_key = self.kwargs.get('vm_images_key')
        self.publish_offer = self.kwargs.get('publish_offer', False)
        self.region = self.kwargs.get('region')
        self.source_container = self.kwargs.get('source_container')
        self.source_resource_group = self.kwargs.get('source_resource_group')
        self.source_storage_account = self.kwargs.get('source_storage_account')
        self.label = self.kwargs.get('label')
        self.offer_id = self.kwargs.get('offer_id')
        self.publisher_id = self.kwargs.get('publisher_id')
        self.sku = self.kwargs.get('sku')
        self.generation_id = self.kwargs.get('generation_id')
        self.cloud_image_name_generation_suffix = self.kwargs.get(
            'cloud_image_name_generation_suffix'
        )

    def get_deprecate_message(self):
        """
        Build deprecate job message.
        """
        deprecate_message = {
            'deprecate_job': {
                'cloud': self.cloud
            }
        }
        deprecate_message['deprecate_job'].update(self.base_message)

        return JsonFormat.json_message(deprecate_message)

    def get_publish_message(self):
        """
        Build publish job message.
        """
        publish_message = {
            'publish_job': {
                'image_description': self.image_description,
                'label': self.label,
                'offer_id': self.offer_id,
                'cloud': self.cloud,
                'publisher_id': self.publisher_id,
                'sku': self.sku,
                'publish_offer': self.publish_offer,
                'account': self.cloud_account,
                'region': self.region,
                'container': self.source_container,
                'resource_group': self.source_resource_group,
                'storage_account': self.source_storage_account
            }
        }

        if self.vm_images_key:
            publish_message['publish_job']['vm_images_key'] = \
                self.vm_images_key

        if self.generation_id:
            publish_message['publish_job']['generation_id'] = \
                self.generation_id

        if self.cloud_image_name_generation_suffix:
            publish_message['publish_job']['cloud_image_name_generation_suffix'] = \
                self.cloud_image_name_generation_suffix

        publish_message['publish_job'].update(self.base_message)

        return JsonFormat.json_message(publish_message)

    def get_replicate_message(self):
        """
        Build replicate job message and publish to replicate exchange.
        """
        replicate_message = {
            'replicate_job': {
                'cloud': self.cloud
            }
        }
        replicate_message['replicate_job'].update(self.base_message)

        return JsonFormat.json_message(replicate_message)

    def get_test_message(self):
        """
        Build test job message.
        """
        test_message = {
            'test_job': {
                'cloud': self.cloud,
                'tests': self.tests,
                'account': self.cloud_account,
                'region': self.region,
                'container': self.source_container,
                'resource_group': self.source_resource_group,
                'storage_account': self.source_storage_account
            }
        }

        if self.distro:
            test_message['test_job']['distro'] = self.distro

        if self.instance_type:
            test_message['test_job']['instance_type'] = \
                self.instance_type

        if self.last_service == 'test' and \
                self.cleanup_images in [True, None]:
            test_message['test_job']['cleanup_images'] = True

        elif self.cleanup_images is False:
            test_message['test_job']['cleanup_images'] = False

        if self.cloud_architecture:
            test_message['test_job']['cloud_architecture'] = \
                self.cloud_architecture

        test_message['test_job'].update(self.base_message)

        return JsonFormat.json_message(test_message)

    def get_upload_message(self):
        """
        Build upload job message.
        """
        upload_message = {
            'upload_job': {
                'cloud_image_name': self.cloud_image_name,
                'cloud': self.cloud,
                'account': self.cloud_account,
                'region': self.region,
                'container': self.source_container,
                'resource_group': self.source_resource_group,
                'storage_account': self.source_storage_account,
                'raw_image_upload_type': self.raw_image_upload_type,
                'raw_image_upload_account': self.raw_image_upload_account,
                'raw_image_upload_location': self.raw_image_upload_location,
                'use_build_time': self.use_build_time,
                'force_replace_image': self.force_replace_image
            }
        }

        if self.additional_uploads:
            upload_message['upload_job']['additional_uploads'] = \
                self.additional_uploads

        upload_message['upload_job'].update(self.base_message)

        return JsonFormat.json_message(upload_message)

    def get_create_message(self):
        """
        Build create job message.
        """
        create_message = {
            'create_job': {
                'cloud': self.cloud,
                'account': self.cloud_account,
                'region': self.region,
                'container': self.source_container,
                'resource_group': self.source_resource_group,
                'storage_account': self.source_storage_account,
                'boot_firmware': self.boot_firmware
            }
        }

        create_message['create_job'].update(self.base_message)

        return JsonFormat.json_message(create_message)
