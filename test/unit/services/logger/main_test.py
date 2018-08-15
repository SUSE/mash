from unittest.mock import patch

from mash.mash_exceptions import MashLoggerException
from mash.services.logger_service import main


class TestLogger(object):
    @patch('mash.services.logger_service.LoggerService')
    def test_main(self, mock_logger_service):
        main()
        mock_logger_service.assert_called_once_with(
            host='localhost', service_exchange='logger',
        )

    @patch('mash.services.logger_service.LoggerService')
    @patch('sys.exit')
    def test_logger_main_mash_error(self, mock_exit, mock_logger_service):
        mock_logger_service.side_effect = MashLoggerException('error')

        main()

        mock_logger_service.assert_called_once_with(
            host='localhost', service_exchange='logger',
        )
        mock_exit.assert_called_once_with(1)

    @patch('mash.services.logger_service.LoggerService')
    @patch('sys.exit')
    def test_logger_main_keyboard_interrupt(
        self, mock_exit, mock_logger_service
    ):
        mock_logger_service.side_effect = KeyboardInterrupt()

        main()
        mock_exit.assert_called_once_with(0)

    @patch('mash.services.logger_service.LoggerService')
    @patch('sys.exit')
    def test_logger_main_system_exit(self, mock_exit, mock_logger_service):
        mock_logger_service.side_effect = SystemExit()

        main()
        mock_exit.assert_called_once_with(0)

    @patch('mash.services.logger_service.LoggerService')
    @patch('sys.exit')
    def test_logger_main_unexpected_error(
        self, mock_exit, mock_logger_service
    ):
        mock_logger_service.side_effect = Exception('Error!')

        main()
        mock_exit.assert_called_once_with(1)
