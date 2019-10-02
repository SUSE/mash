from unittest.mock import Mock, patch

from mash.services.api.utils.amqp import connect, publish


@patch('mash.services.api.utils.amqp.current_app')
@patch('mash.services.api.utils.amqp.Connection')
def test_connect(mock_connection, mock_current_app):
    connection = Mock()
    channel = Mock()
    connection.channel.return_value = channel
    mock_connection.return_value = connection

    connect()
    channel.confirm_deliveries.assert_called_once_with()


@patch('mash.services.api.utils.amqp.connect')
@patch('mash.services.api.utils.amqp.current_app')
@patch('mash.services.api.utils.amqp.channel')
def test_publish(mock_channel, mock_current_app, mock_connect):
    mock_channel.closed = True
    publish('testing', 'doc', 'msg')

    mock_connect.assert_called_once_with()
    mock_channel.basic.publish.assert_called_once_with(
        body='msg',
        routing_key='doc',
        exchange='testing',
        properties={
            'content_type': 'application/json',
            'delivery_mode': 2
        },
        mandatory=True
    )