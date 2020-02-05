# Copyright (c) 2020 SUSE LLC.  All rights reserved.
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

import copy

from mash.services.api.schema import string_with_example
from mash.services.api.schema.jobs import base_job_message

oci_job_message = copy.deepcopy(base_job_message)
oci_job_message['properties']['cloud_account'] = string_with_example(
    'account1'
)
oci_job_message['properties']['bucket'] = string_with_example('images')
oci_job_message['properties']['region'] = string_with_example('us-phoenix-1')
oci_job_message['properties']['availability_domain'] = string_with_example('Omic:PHX-AD-1')
oci_job_message['properties']['compartment_id'] = string_with_example('ocid1.compartment.oc1..')
oci_job_message['properties']['operating_system'] = string_with_example('SLES')
oci_job_message['properties']['operating_system_version'] = string_with_example('12SP1')
oci_job_message['properties']['image_type'] = {
    'type': 'string',
    'enum': ['QCOW2', 'VMDK']
}
oci_job_message['properties']['launch_mode'] = {
    'type': 'string',
    'enum': ['NATIVE', 'EMULATED', 'PARAVIRTUALIZED', 'CUSTOM']
}
oci_job_message['properties']['image']['example'] = 'openSUSE-Leap-15.0-oci'
oci_job_message['properties']['cloud_image_name']['example'] = \
    'opensuse-leap-15-v{date}'
oci_job_message['properties']['old_cloud_image_name']['example'] = \
    'opensuse-leap-15-v20190520'
oci_job_message['properties']['image_description']['example'] = \
    'openSUSE Leap 15'
oci_job_message['properties']['instance_type']['example'] = 'VM.Standard2.1'

oci_job_message['required'].append('cloud_account')
oci_job_message['required'].append('operating_system')
oci_job_message['required'].append('operating_system_version')