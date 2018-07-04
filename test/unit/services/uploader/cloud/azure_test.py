from pytest import raises
from unittest.mock import (
    MagicMock, Mock, patch, call
)
from test.unit.test_helper import (
    patch_open, context_manager
)
from collections import namedtuple

from mash.services.uploader.cloud.azure import UploadAzure
from mash.mash_exceptions import MashUploadException
from mash.utils.json_format import JsonFormat

from azure.mgmt.storage import StorageManagementClient
from azure.mgmt.compute import ComputeManagementClient


class TestUploadAzure(object):
    @patch('mash.services.uploader.cloud.azure.NamedTemporaryFile')
    @patch_open
    def setup(self, mock_open, mock_NamedTemporaryFile):
        open_context = context_manager()
        mock_open.return_value = open_context.context_manager_mock
        tempfile = Mock()
        tempfile.name = 'tempfile'
        mock_NamedTemporaryFile.return_value = tempfile
        self.credentials = Mock()
        self.credentials = {
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
        custom_args = {
            'resource_group': 'group_name',
            'container_name': 'container',
            'storage_account': 'storage',
            'region': 'region'
        }
        self.uploader = UploadAzure(
            self.credentials, 'file', 'name', 'description', custom_args
        )
        open_context.file_mock.write.assert_called_once_with(
            JsonFormat.json_message(self.credentials)
        )

    @patch('mash.services.uploader.cloud.azure.NamedTemporaryFile')
    @patch_open
    def test_init_incomplete_arguments(
        self, mock_open, mock_NamedTemporaryFile
    ):
        custom_args = {
            'resource_group': 'group_name',
            'container_name': 'container',
            'storage_account': 'storage',
            'region': 'region'
        }
        del custom_args['storage_account']
        with raises(MashUploadException):
            UploadAzure(
                self.credentials, 'file', 'name', 'description', custom_args
            )
        del custom_args['container_name']
        with raises(MashUploadException):
            UploadAzure(
                self.credentials, 'file', 'name', 'description', custom_args
            )
        del custom_args['region']
        with raises(MashUploadException):
            UploadAzure(
                self.credentials, 'file', 'name', 'description', custom_args
            )
        with raises(MashUploadException):
            UploadAzure(
                self.credentials, 'file', 'name', 'description', None
            )

    @patch('mash.services.uploader.cloud.azure.get_client_from_auth_file')
    @patch('mash.services.uploader.cloud.azure.PageBlobService')
    @patch('mash.services.uploader.cloud.azure.PageBlob')
    @patch('mash.services.uploader.cloud.azure.FileType')
    @patch('mash.services.uploader.cloud.azure.lzma')
    @patch('builtins.open')
    def test_upload(
        self, mock_open, mock_lzma, mock_FileType,
        mock_PageBlob, mock_PageBlobService, mock_get_client_from_auth_file
    ):
        lzma_handle = MagicMock()
        lzma_handle.__enter__.return_value = lzma_handle
        mock_lzma.LZMAFile.return_value = lzma_handle
        open_handle = MagicMock()
        open_handle.__enter__.return_value = open_handle
        mock_open.return_value = open_handle
        client = MagicMock()
        mock_get_client_from_auth_file.return_value = client
        page_blob_service = Mock()
        mock_PageBlobService.return_value = page_blob_service
        key_type = namedtuple('key_type', ['value', 'key_name'])
        async_create_image = Mock()
        storage_key_list = Mock()
        storage_key_list.keys = [
            key_type(value='key', key_name='key_name')
        ]
        client.storage_accounts.list_keys.return_value = storage_key_list
        client.images.create_or_update.return_value = async_create_image

        system_image_file_type = Mock()
        system_image_file_type.get_size.return_value = 1024
        system_image_file_type.is_xz.return_value = True
        mock_FileType.return_value = system_image_file_type

        page_blob = Mock()
        next_results = [3, 2, 1]

        def side_effect(stream):
            try:
                return next_results.pop()
            except Exception:
                raise StopIteration

        page_blob.next.side_effect = side_effect
        mock_PageBlob.return_value = page_blob

        assert self.uploader.upload() == ('name', 'region')

        assert mock_get_client_from_auth_file.call_args_list == [
            call(StorageManagementClient, auth_path='tempfile'),
            call(ComputeManagementClient, auth_path='tempfile')
        ]
        client.storage_accounts.list_keys.assert_called_once_with(
            'group_name', 'storage'
        )
        mock_PageBlobService.assert_called_once_with(
            account_key='key', account_name='storage'
        )
        mock_PageBlob.assert_called_once_with(
            page_blob_service, 'name', 'container', 1024
        )
        assert page_blob.next.call_args_list == [
            call(mock_lzma.LZMAFile.return_value),
            call(mock_lzma.LZMAFile.return_value),
            call(mock_lzma.LZMAFile.return_value),
            call(mock_lzma.LZMAFile.return_value)
        ]
        mock_FileType.assert_called_once_with('file')
        system_image_file_type.is_xz.assert_called_once_with()
        client.images.create_or_update.assert_called_once_with(
            'group_name', 'name', {
                'location': 'region', 'storage_profile': {
                    'os_disk': {
                        'blob_uri':
                        'https://storage.blob.core.windows.net/container/name',
                        'os_type': 'Linux',
                        'caching': 'ReadWrite',
                        'os_state': 'Generalized'
                    }
                }
            }
        )
        async_create_image.wait.assert_called_once_with()

        system_image_file_type.is_xz.return_value = False
        page_blob.reset_mock()
        next_results = [3, 2, 1]

        self.uploader.upload()

        assert page_blob.next.call_args_list == [
            call(mock_open.return_value),
            call(mock_open.return_value),
            call(mock_open.return_value),
            call(mock_open.return_value)
        ]