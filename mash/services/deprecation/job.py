# Copyright (c) 2018 SUSE Linux GmbH.  All rights reserved.
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

from mash.services.status_levels import UNKOWN
from mash.services.deprecation.constants import NOT_IMPLEMENTED


class DeprecationJob(object):
    """
    Class for an individual deprecation job.
    """

    def __init__(self, id, provider, utctime, job_file=None):
        self.iteration_count = 0
        self.id = id
        self.job_file = job_file
        self.log_callback = None
        self.provider = provider
        self.status = UNKOWN
        self.utctime = utctime

    def _deprecate(self):
        """
        Deprecate image to all regions in each account.
        """
        raise NotImplementedError(NOT_IMPLEMENTED)

    def get_metadata(self):
        """
        Return dictionary of metadata based on job.
        """
        return {'job_id': self.id}

    def deprecate_image(self):
        """
        Deprecate image.
        """
        self.iteration_count += 1
        self._deprecate()

    def send_log(self, message, success=True):
        if self.log_callback:
            self.log_callback(
                'Pass[{0}]: {1}'.format(
                    self.iteration_count,
                    message
                ),
                self.get_metadata(),
                success
            )

    def set_log_callback(self, callback):
        """
        Set log_callback function to callback.
        """
        self.log_callback = callback