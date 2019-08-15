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

import io

from pytest import raises
from unittest.mock import call, MagicMock, patch

from mash.mash_exceptions import MashException
from mash.utils.json_format import JsonFormat
from mash.utils.mash_utils import (
    create_json_file,
    generate_name,
    get_key_from_file,
    create_ssh_key_pair,
    format_string_with_date,
    remove_file,
    persist_json,
    load_json,
    restart_job,
    restart_jobs,
    handle_request
)


@patch('mash.utils.mash_utils.os')
@patch('mash.utils.mash_utils.NamedTemporaryFile')
def test_create_json_file(mock_temp_file, mock_os):
    json_file = MagicMock()
    json_file.name = 'test.json'
    mock_temp_file.return_value = json_file

    data = {'tenantId': '123456', 'subscriptionId': '98765'}
    with patch('builtins.open', create=True) as mock_open:
        mock_open.return_value = MagicMock(spec=io.IOBase)
        with create_json_file(data) as json_file:
            assert json_file == 'test.json'

        file_handle = mock_open.return_value.__enter__.return_value
        file_handle.write.assert_called_with(JsonFormat.json_message(data))

    mock_os.remove.assert_called_once_with('test.json')


def test_generate_name():
    result = generate_name(10)
    assert len(result) == 10


def test_get_key_from_file():
    with patch('builtins.open', create=True) as mock_open:
        mock_open.return_value = MagicMock(spec=io.IOBase)
        file_handle = mock_open.return_value.__enter__.return_value
        file_handle.read.return_value = 'fakekey'
        result = get_key_from_file('my-key.file')

    assert result == 'fakekey'


@patch('mash.utils.mash_utils.rsa')
def test_create_ssh_key_pair(mock_rsa):
    private_key = MagicMock()
    public_key = MagicMock()

    public_key.public_bytes.return_value = b'0987654321'

    private_key.public_key.return_value = public_key
    private_key.private_bytes.return_value = b'1234567890'

    mock_rsa.generate_private_key.return_value = private_key

    with patch('builtins.open', create=True) as mock_open:
        mock_open.return_value = MagicMock(spec=io.IOBase)
        create_ssh_key_pair('/temp.key')
        file_handle = mock_open.return_value.__enter__.return_value
        file_handle.write.assert_has_calls([
            call(b'1234567890'),
            call(b'0987654321')
        ])


def test_format_string_with_date_error():
    value = 'Name with a {timestamp}'
    format_string_with_date(value)


@patch('mash.utils.mash_utils.os.remove')
def test_remove_file(mock_remove):
    mock_remove.side_effect = FileNotFoundError('File not found.')
    remove_file('job-test.json')
    mock_remove.assert_called_once_with('job-test.json')


def test_persist_json():
    with patch('builtins.open', create=True) as mock_open:
        mock_open.return_value = MagicMock(spec=io.IOBase)

        persist_json('tmp-dir/job-1.json', {'id': '1'})

        file_handle = mock_open.return_value.__enter__.return_value
        file_handle.write.assert_called_with('{\n    "id": "1"\n}')


@patch('mash.utils.mash_utils.json.load')
def test_load_json(mock_load_json):
    mock_load_json.return_value = {'id': '123'}

    with patch('builtins.open', create=True) as mock_open:
        mock_open.return_value = MagicMock(spec=io.IOBase)

        data = load_json('tmp/job-123.json')

        file_handle = mock_open.return_value.__enter__.return_value
        file_handle.read.call_count == 1

    assert data['id'] == '123'


@patch('mash.utils.mash_utils.load_json')
def test_restart_job(mock_json_load):
    mock_json_load.return_value = {'id': '123'}
    callback = MagicMock()

    restart_job('tmp/job-123.json', callback)
    mock_json_load.assert_called_once_with(
        'tmp/job-123.json'
    )
    callback.assert_called_once_with({'id': '123'})


@patch('mash.utils.mash_utils.restart_job')
@patch('mash.utils.mash_utils.os.listdir')
def test_restart_jobs(mock_os_listdir, mock_restart_job):
    mock_os_listdir.return_value = ['job-123.json']
    callback = MagicMock()

    restart_jobs('tmp/', callback)
    mock_restart_job.assert_called_once_with(
        'tmp/job-123.json',
        callback
    )


@patch('mash.utils.mash_utils.requests')
def test_handle_request(mock_requests):
    response = MagicMock()
    response.status_code = 200
    mock_requests.get.return_value = response

    result = handle_request('localhost', '/jobs', 'get')
    assert result == response


@patch('mash.utils.mash_utils.requests')
def test_handle_request_failed(mock_requests):
    response = MagicMock()
    response.status_code = 400
    response.json.return_value = {}
    mock_requests.get.return_value = response

    with raises(MashException):
        handle_request('localhost', '/jobs', 'get')
