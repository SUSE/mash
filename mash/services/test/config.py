# Copyright (c) 2018 SUSE LLC.  All rights reserved.
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

from mash.services.base_config import BaseConfig
from mash.services.test.defaults import Defaults


class TestConfig(BaseConfig):
    """
    Implements reading of test configuration from the mash
    configuration file:

    * /etc/mash/mash_config.yaml

    The mash configuration file is a yaml formatted file containing
    information to control the behavior of the mash services.
    """
    __test__ = False  # Used by pytest to ignore class in auto discovery

    def __init__(self, config_file=None):
        super(TestConfig, self).__init__(config_file)

    def get_img_proof_timeout(self):
        """
        Return the img-proof timeout value in seconds.

        :rtype: int
        """
        img_proof_timeout = self._get_attribute(
            attribute='img_proof_timeout',
            element='test'
        )
        return img_proof_timeout or Defaults.get_img_proof_timeout()
