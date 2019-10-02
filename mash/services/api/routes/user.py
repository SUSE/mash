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

import json

from flask import jsonify, request, make_response
from flask_restplus import fields, marshal, Namespace, Resource

from flask_jwt_extended import (
    jwt_required,
    get_jwt_identity
)

from mash.mash_exceptions import MashDBException
from mash.services.api.schema import (
    add_account,
    default_response,
    validation_error
)
from mash.services.api.utils.users import add_user, get_user_by_username, delete_user

api = Namespace(
    'User',
    description='User operations'
)
get_account_response = api.model(
    'get_account_response', {
        'id': fields.String,
        'username': fields.String,
        'email': fields.String
    }
)
add_account_request = api.schema_model(
    'add_account_request', add_account
)
validation_error_response = api.schema_model(
    'validation_error', validation_error
)

api.models['default_response'] = default_response


@api.route('/')
class Account(Resource):
    @api.doc('create_mash_account')
    @api.expect(add_account_request)
    @api.response(201, 'Created account', get_account_response)
    @api.response(400, 'Validation error', validation_error_response)
    @api.response(409, 'Already in use', default_response)
    def post(self):
        """
        Create a new MASH account.
        """
        data = json.loads(request.data.decode())

        try:
            user = add_user(data['username'], data['email'], data['password'])
        except MashDBException as error:
            return make_response(
                jsonify({
                    "errors": {"password": str(error)},
                    "message": "Input payload validation failed"
                }),
                400
            )

        if user:
            return make_response(
                jsonify(marshal(user, get_account_response)),
                201
            )
        else:
            return make_response(
                jsonify({'msg': 'Username or email already in use'}),
                409
            )

    @api.doc('get_mash_account')
    @api.doc(security='apiKey')
    @api.marshal_with(get_account_response)
    @jwt_required
    @api.response(401, 'Unauthorized', default_response)
    @api.response(422, 'Not processable', default_response)
    def get(self):
        """
        Returns MASH account.
        """
        user = get_user_by_username(get_jwt_identity())
        return user

    @api.doc('delete_mash_account')
    @api.doc(security='apiKey')
    @jwt_required
    @api.response(200, 'Account deleted', default_response)
    @api.response(400, 'Delete account failed', default_response)
    @api.response(401, 'Unauthorized', default_response)
    @api.response(422, 'Not processable', default_response)
    def delete(self):
        """
        Delete MASH account.
        """
        rows_deleted = delete_user(get_jwt_identity())

        if rows_deleted:
            return make_response(
                jsonify({'msg': 'Account deleted'}),
                200
            )
        else:
            return make_response(
                jsonify({'msg': 'Delete account failed'}),
                400
            )