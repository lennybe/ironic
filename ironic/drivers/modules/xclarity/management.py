#    Copyright 2017 Lenovo, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.


from ironic_lib import metrics_utils
from oslo_log import log as logging
from oslo_utils import importutils

from ironic.common import boot_devices
from ironic.common import exception
from ironic.common.i18n import _
from ironic.conductor import task_manager
from ironic.drivers import base
from ironic.drivers.modules.xclarity import common

LOG = logging.getLogger(__name__)

METRICS = metrics_utils.get_metrics_logger(__name__)

xclarity_client_exceptions = importutils.try_import(
    'xclarity_client.exceptions')

BOOT_DEVICE_MAPPING_TO_XCLARITY = {
    boot_devices.PXE: 'PXE Network',
    boot_devices.DISK: 'Hard Disk 0',
    boot_devices.CDROM: 'CD/DVD Rom',
    boot_devices.BIOS: 'Boot To F1'
}

SUPPORTED_BOOT_DEVICES = [
    boot_devices.PXE,
    boot_devices.DISK,
    boot_devices.CDROM,
    boot_devices.BIOS,
]


class XClarityManagement(base.ManagementInterface):
    def __init__(self):
        super(XClarityManagement, self).__init__()
        self.xclarity_client = common.get_xclarity_client()

    def get_properties(self):
        return common.COMMON_PROPERTIES

    @METRICS.timer('XClarityManagement.validate')
    def validate(self, task):
        """It validates if the node is being used by XClarity.

        :param task: a task from TaskManager.
        """
        common.is_node_managed_by_xclarity(self.xclarity_client, task.node)

    @METRICS.timer('XClarityManagement.get_supported_boot_devices')
    def get_supported_boot_devices(self, task):
        """Gets a list of the supported boot devices.

        :param task: a task from TaskManager.
        :returns: A list with the supported boot devices defined
                  in :mod:`ironic.common.boot_devices`.
        """

        return SUPPORTED_BOOT_DEVICES

    def _validate_supported_boot_device(self, task, boot_device):
        """It validates if the boot device is supported by XClarity.

        :param task: a task from TaskManager.
        :param boot_device: the boot device, one of [PXE, DISK, CDROM, BIOS]
        :raises: InvalidParameterValue if the boot device is not supported.
        """
        if boot_device not in SUPPORTED_BOOT_DEVICES:
            raise exception.InvalidParameterValue(
                _("Unsupported boot device %(device)s for node: %(node)s ")
                % {"device": boot_device, "node": task.node.uuid}
            )

    @METRICS.timer('XClarityManagement.get_boot_device')
    def get_boot_device(self, task):
        """Get the current boot device for the task's node.

        :param task: a task from TaskManager.
        :returns: a dictionary containing:
            :boot_device: the boot device, one of [PXE, DISK, CDROM, BIOS]
            :persistent: Whether the boot device will persist or not
        :raises: InvalidParameterValue if the boot device is unknown
        :raises: XClarityError if the communication with XClarity fails
        """
        server_hardware_id = common.get_server_hardware_id(task.node)
        try:
            boot_info = (
                self.xclarity_client.get_node_all_boot_info(
                    server_hardware_id)
            )
        except xclarity_client_exceptions.XClarityError as xclarity_exc:
            LOG.error(
                "Error getting boot device from XClarity for node %(node)s. "
                "Error: %(error)s", {'node': task.node.uuid,
                                     'error': xclarity_exc})
            raise exception.XClarityError(error=xclarity_exc)

        persistent = False
        primary = None
        boot_order = boot_info['bootOrder']['bootOrderList']
        for item in boot_order:
            current = item.get('currentBootOrderDevices', None)
            boot_type = item.get('bootType', None)
            if boot_type == "SingleUse":
                persistent = False
                primary = current[0]
                if primary != 'None':
                    boot_device = {'boot_device': primary,
                                   'persistent': persistent}
                    self._validate_whether_supported_boot_device(primary)
                    return boot_device
            elif boot_type == "Permanent":
                persistent = True
                boot_device = {'boot_device': current[0],
                               'persistent': persistent}
                self._validate_supported_boot_device(task, primary)
                return boot_device

    @METRICS.timer('XClarityManagement.set_boot_device')
    @task_manager.require_exclusive_lock
    def set_boot_device(self, task, device, persistent=False):
        """Sets the boot device for a node.

        :param task: a task from TaskManager.
        :param device: the boot device, one of the supported devices
                       listed in :mod:`ironic.common.boot_devices`.
        :param persistent: Boolean value. True if the boot device will
                           persist to all future boots, False if not.
                           Default: False.
        :raises: InvalidParameterValue if an invalid boot device is
                 specified.
        :raises: XClarityError if the communication with XClarity fails
        """
        self._validate_supported_boot_device(task=task, boot_device=device)

        server_hardware_id = task.node.driver_info.get('server_hardware_id')
        LOG.debug("Setting boot device to %(device)s for node %(node)s",
                  {"device": device, "node": task.node.uuid})
        self._set_boot_device(task, server_hardware_id, device,
                              singleuse=not persistent)

    @METRICS.timer('XClarityManagement.get_sensors_data')
    def get_sensors_data(self, task):
        """Get sensors data.

        :param task: a TaskManager instance.
        :raises: NotImplementedError

        """
        raise NotImplementedError()

    def _translate_ironic_to_xclarity(self, boot_device):
        """Translates Ironic boot options to Xclarity boot options.

        :param boot_device: Ironic boot_device
        :returns: Translated XClarity boot_device.

        """
        return BOOT_DEVICE_MAPPING_TO_XCLARITY.get(boot_device)

    def _set_boot_device(self, task, server_hardware_id,
                         new_primary_boot_device, singleuse=False):
        """Set the current boot device for xclarity

        :param server_hardware_id: the uri of the server hardware in XClarity
        :param new_primary_boot_device: boot device to be set
        :param task: a TaskManager instance.
        :param singleuse: if this device will be used only once at next boot
        """
        boot_info = self.xclarity_client.get_node_all_boot_info(
            server_hardware_id)
        xclarity_boot_device = self._translate_ironic_to_xclarity(
            new_primary_boot_device)
        current = []
        LOG.debug(
            ("Setting boot device to %(device)s for XClarity "
             "node %(node)s"),
            {'device': xclarity_boot_device, 'node': task.node.uuid}
        )
        for item in boot_info['bootOrder']['bootOrderList']:
            if singleuse and item['bootType'] == 'SingleUse':
                item['currentBootOrderDevices'][0] = xclarity_boot_device
            elif not singleuse and item['bootType'] == 'Permanent':
                current = item['currentBootOrderDevices']
                if xclarity_boot_device == current[0]:
                    return
                if xclarity_boot_device in current:
                    current.remove(xclarity_boot_device)
                current.insert(0, xclarity_boot_device)
                item['currentBootOrderDevices'] = current

        try:
            self.xclarity_client.set_node_boot_info(server_hardware_id,
                                                    boot_info,
                                                    xclarity_boot_device,
                                                    singleuse)
        except xclarity_client_exceptions.XClarityError as xclarity_exc:
            LOG.error(
                ('Error setting boot device %(boot_device)s for the XClarity '
                 'node %(node)s. Error: %(error)s'),
                {'boot_device': xclarity_boot_device, 'node': task.node.uuid,
                 'error': xclarity_exc}
            )
            raise exception.XClarityError(error=xclarity_exc)
