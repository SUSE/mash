from pytest import raises
from unittest.mock import (
    MagicMock, Mock, patch, call
)

from mash.services.create.azure_job import AzureCreateJob
from mash.mash_exceptions import MashCreateException
from mash.services.base_config import BaseConfig


class TestAzureCreateJob(object):
    def setup(self):
        self.credentials = {
            'test': {
                'clientId': 'a',
                'clientSecret': 'b',
                'subscriptionId': 'c',
                'tenantId': 'd',
                'activeDirectoryEndpointUrl':
                    'https://login.microsoftonline.com',
                'resourceManagerEndpointUrl':
                    'https://management.azure.com/',
                'activeDirectoryGraphResourceId':
                    'https://graph.windows.net/',
                'sqlManagementEndpointUrl':
                    'https://management.core.windows.net:8443/',
                'galleryEndpointUrl':
                    'https://gallery.azure.com/',
                'managementEndpointUrl':
                    'https://management.core.windows.net/'
            }
        }
        job_doc = {
            'id': '1',
            'last_service': 'create',
            'cloud': 'azure',
            'requesting_user': 'user1',
            'utctime': 'now',
            'account': 'test',
            'resource_group': 'group_name',
            'container': 'container',
            'storage_account': 'storage',
            'region': 'region',
            'cloud_image_name': 'name',
            'boot_firmware': ['bios', 'uefi']
        }

        self.config = BaseConfig(
            config_file='test/data/mash_config.yaml'
        )

        self.job = AzureCreateJob(job_doc, self.config)
        self.job.credentials = self.credentials
        self.job._log_callback = Mock()

    def test_post_init_incomplete_arguments(self):
        job_doc = {
            'cloud_architecture': 'aarch64',
            'id': '1',
            'last_service': 'create',
            'requesting_user': 'user1',
            'cloud': 'gce',
            'utctime': 'now'
        }

        with raises(MashCreateException):
            AzureCreateJob(job_doc, self.config)

    @patch('mash.services.create.azure_job.delete_image')
    @patch('mash.services.create.azure_job.image_exists')
    @patch('mash.services.create.azure_job.get_client_from_json')
    @patch('builtins.open')
    def test_create(
        self,
        mock_open,
        mock_get_client_from_json,
        mock_image_exists,
        mock_delete_image
    ):
        open_handle = MagicMock()
        open_handle.__enter__.return_value = open_handle
        mock_open.return_value = open_handle
        mock_image_exists.return_value = False

        client = MagicMock()
        mock_get_client_from_json.return_value = client

        async_create_image = Mock()
        client.images.begin_create_or_update.return_value = async_create_image

        self.job.status_msg['cloud_image_name'] = 'name'
        self.job.status_msg['blob_name'] = 'name.vhd'
        self.job.run_job()

        assert mock_get_client_from_json.call_count == 2
        client.images.begin_create_or_update.has_calls(
            call(
                'group_name', 'name', {
                    'location': 'region',
                    'hyper_v_generation': 'V1',
                    'storage_profile': {
                        'os_disk': {
                            'blob_uri':
                            'https://storage.blob.core.windows.net/'
                            'container/name.vhd',
                            'os_type': 'Linux',
                            'caching': 'ReadWrite',
                            'os_state': 'Generalized'
                        }
                    }
                }
            ),
            call(
                'group_name', 'name_uefi', {
                    'location': 'region',
                    'hyper_v_generation': 'V2',
                    'storage_profile': {
                        'os_disk': {
                            'blob_uri':
                                'https://storage.blob.core.windows.net/'
                                'container/name.vhd',
                            'os_type': 'Linux',
                            'caching': 'ReadWrite',
                            'os_state': 'Generalized'
                        }
                    }
                }
            )
        )
        assert async_create_image.result.call_count == 2

        # Image exists
        mock_image_exists.return_value = True
        self.job.run_job()

        assert mock_delete_image.call_count == 2
