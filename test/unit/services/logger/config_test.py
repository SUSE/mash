from unittest.mock import patch

from mash.services.logger.config import LoggerConfig


class TestLoggerConfig(object):
    def setup(self):
        self.config = LoggerConfig('../data/logger_config.yml')
        self.empty_config = LoggerConfig('../data/empty_logger_config.yml')

    def test_get_log_dir(self):
        assert self.config.get_log_directory() == '/var/log/mash/'
        assert self.empty_config.get_log_directory() == '/var/log/mash/'

    @patch.object(LoggerConfig, 'get_log_directory')
    def test_get_job_log_file(self, mock_get_log_dir):
        mock_get_log_dir.return_value = '/var/log/mash/'
        assert self.empty_config.get_job_log_file('1234') == \
            '/var/log/mash/job_1234.log'