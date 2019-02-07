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

from mash.services.deprecation.job import DeprecationJob
from mash.services.status_levels import SUCCESS


class AzureDeprecationJob(DeprecationJob):
    """
    Class for an Azure deprecation job.
    """

    def __init__(
        self, id, last_service, cloud, utctime,
        old_cloud_image_name=None, job_file=None
    ):
        super(AzureDeprecationJob, self).__init__(
            id, last_service, cloud, utctime,
            old_cloud_image_name=old_cloud_image_name, job_file=job_file
        )

        # Skip credential request since there is no deprecation in Azure
        self.credentials = {'status': 'no deprecation'}

    def _deprecate(self):
        """
        There is no deprecation process in Azure.
        """
        self.status = SUCCESS