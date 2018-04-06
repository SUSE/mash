from pytest import raises
from unittest.mock import patch

from mash.mash_exceptions import MashDeprecationException
from mash.services.deprecation_service import main


class TestDeprecationServiceMain(object):
    @patch('mash.services.deprecation_service.DeprecationService')
    def test_main(self, mock_deprecation_service):
        main()
        mock_deprecation_service.assert_called_once_with(
            host='localhost', service_exchange='deprecation',
        )

    @patch('mash.services.deprecation_service.DeprecationService')
    @patch('sys.exit')
    def test_deprecation_main_mash_error(
        self, mock_exit, mock_deprecation_service
    ):
        mock_deprecation_service.side_effect = MashDeprecationException(
            'error'
        )

        main()

        mock_deprecation_service.assert_called_once_with(
            host='localhost', service_exchange='deprecation',
        )
        mock_exit.assert_called_once_with(1)

    @patch('mash.services.deprecation_service.DeprecationService')
    @patch('sys.exit')
    def test_deprecation_main_system_exit(
        self, mock_exit, mock_deprecation_service
    ):
        mock_deprecation_service.side_effect = SystemExit()

        main()
        mock_exit.assert_called_once_with(mock_deprecation_service.side_effect)

    @patch('mash.services.deprecation_service.DeprecationService')
    def test_deprecation_main_unexpected_error(self, mock_deprecation_service):
        mock_deprecation_service.side_effect = Exception('Error!')

        with raises(Exception):
            main()