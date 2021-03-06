# coding=utf-8
#
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

from oslo_utils import strutils
from oslo_utils import uuidutils
from oslo_utils import versionutils
from oslo_versionedobjects import base as object_base

from ironic.common import exception
from ironic.common.i18n import _
from ironic.db import api as db_api
from ironic import objects
from ironic.objects import base
from ironic.objects import fields as object_fields
from ironic.objects import notification

REQUIRED_INT_PROPERTIES = ['local_gb', 'cpus', 'memory_mb']


@base.IronicObjectRegistry.register
class Node(base.IronicObject, object_base.VersionedObjectDictCompat):
    # Version 1.0: Initial version
    # Version 1.1: Added instance_info
    # Version 1.2: Add get() and get_by_id() and make get_by_uuid()
    #              only work with a uuid
    # Version 1.3: Add create() and destroy()
    # Version 1.4: Add get_by_instance_uuid()
    # Version 1.5: Add list()
    # Version 1.6: Add reserve() and release()
    # Version 1.7: Add conductor_affinity
    # Version 1.8: Add maintenance_reason
    # Version 1.9: Add driver_internal_info
    # Version 1.10: Add name and get_by_name()
    # Version 1.11: Add clean_step
    # Version 1.12: Add raid_config and target_raid_config
    # Version 1.13: Add touch_provisioning()
    # Version 1.14: Add _validate_property_values() and make create()
    #               and save() validate the input of property values.
    # Version 1.15: Add get_by_port_addresses
    # Version 1.16: Add network_interface field
    # Version 1.17: Add resource_class field
    # Version 1.18: Add default setting for network_interface
    # Version 1.19: Add fields: boot_interface, console_interface,
    #               deploy_interface, inspect_interface, management_interface,
    #               power_interface, raid_interface, vendor_interface
    # Version 1.20: Type of network_interface changed to just nullable string
    # Version 1.21: Add storage_interface field
    # Version 1.22: Add rescue_interface field
    # Version 1.23: Add traits field
    # Version 1.24: Add bios_interface field
    # Version 1.25: Add fault field
    VERSION = '1.25'

    dbapi = db_api.get_instance()

    fields = {
        'id': object_fields.IntegerField(),

        'uuid': object_fields.UUIDField(nullable=True),
        'name': object_fields.StringField(nullable=True),
        'chassis_id': object_fields.IntegerField(nullable=True),
        'instance_uuid': object_fields.UUIDField(nullable=True),

        'driver': object_fields.StringField(nullable=True),
        'driver_info': object_fields.FlexibleDictField(nullable=True),
        'driver_internal_info': object_fields.FlexibleDictField(nullable=True),

        # A clean step dictionary, indicating the current clean step
        # being executed, or None, indicating cleaning is not in progress
        # or has not yet started.
        'clean_step': object_fields.FlexibleDictField(nullable=True),

        'raid_config': object_fields.FlexibleDictField(nullable=True),
        'target_raid_config': object_fields.FlexibleDictField(nullable=True),

        'instance_info': object_fields.FlexibleDictField(nullable=True),
        'properties': object_fields.FlexibleDictField(nullable=True),
        'reservation': object_fields.StringField(nullable=True),
        # a reference to the id of the conductor service, not its hostname,
        # that has most recently performed some action which could require
        # local state to be maintained (eg, built a PXE config)
        'conductor_affinity': object_fields.IntegerField(nullable=True),

        # One of states.POWER_ON|POWER_OFF|NOSTATE|ERROR
        'power_state': object_fields.StringField(nullable=True),

        # Set to one of states.POWER_ON|POWER_OFF when a power operation
        # starts, and set to NOSTATE when the operation finishes
        # (successfully or unsuccessfully).
        'target_power_state': object_fields.StringField(nullable=True),

        'provision_state': object_fields.StringField(nullable=True),
        'provision_updated_at': object_fields.DateTimeField(nullable=True),
        'target_provision_state': object_fields.StringField(nullable=True),

        'maintenance': object_fields.BooleanField(),
        'maintenance_reason': object_fields.StringField(nullable=True),
        'fault': object_fields.StringField(nullable=True),
        'console_enabled': object_fields.BooleanField(),

        # Any error from the most recent (last) asynchronous transaction
        # that started but failed to finish.
        'last_error': object_fields.StringField(nullable=True),

        # Used by nova to relate the node to a flavor
        'resource_class': object_fields.StringField(nullable=True),

        'inspection_finished_at': object_fields.DateTimeField(nullable=True),
        'inspection_started_at': object_fields.DateTimeField(nullable=True),

        'extra': object_fields.FlexibleDictField(nullable=True),

        'bios_interface': object_fields.StringField(nullable=True),
        'boot_interface': object_fields.StringField(nullable=True),
        'console_interface': object_fields.StringField(nullable=True),
        'deploy_interface': object_fields.StringField(nullable=True),
        'inspect_interface': object_fields.StringField(nullable=True),
        'management_interface': object_fields.StringField(nullable=True),
        'network_interface': object_fields.StringField(nullable=True),
        'power_interface': object_fields.StringField(nullable=True),
        'raid_interface': object_fields.StringField(nullable=True),
        'rescue_interface': object_fields.StringField(nullable=True),
        'storage_interface': object_fields.StringField(nullable=True),
        'vendor_interface': object_fields.StringField(nullable=True),
        'traits': object_fields.ObjectField('TraitList', nullable=True),
    }

    def as_dict(self, secure=False):
        d = super(Node, self).as_dict()
        if secure:
            d['driver_info'] = strutils.mask_dict_password(
                d.get('driver_info', {}), "******")
            d['instance_info'] = strutils.mask_dict_password(
                d.get('instance_info', {}), "******")
        return d

    def _validate_property_values(self, properties):
        """Check if the input of local_gb, cpus and memory_mb are valid.

        :param properties: a dict contains the node's information.
        """
        if not properties:
            return
        invalid_msgs_list = []
        for param in REQUIRED_INT_PROPERTIES:
            value = properties.get(param)
            if value is None:
                continue
            try:
                int_value = int(value)
                if int_value < 0:
                    raise ValueError("Value must be non-negative")
            except (ValueError, TypeError):
                msg = (('%(param)s=%(value)s') %
                       {'param': param, 'value': value})
                invalid_msgs_list.append(msg)

        if invalid_msgs_list:
            msg = (_('The following properties for node %(node)s '
                     'should be non-negative integers, '
                     'but provided values are: %(msgs)s') %
                   {'node': self.uuid, 'msgs': ', '.join(invalid_msgs_list)})
            raise exception.InvalidParameterValue(msg)

    def _set_from_db_object(self, context, db_object, fields=None):
        fields = set(fields or self.fields) - {'traits'}
        super(Node, self)._set_from_db_object(context, db_object, fields)
        self.traits = object_base.obj_make_list(
            context, objects.TraitList(context),
            objects.Trait, db_object['traits'])
        self.traits.obj_reset_changes()

    # NOTE(xek): We don't want to enable RPC on this call just yet. Remotable
    # methods can be used in the future to replace current explicit RPC calls.
    # Implications of calling new remote procedures should be thought through.
    # @object_base.remotable_classmethod
    @classmethod
    def get(cls, context, node_id):
        """Find a node based on its id or uuid and return a Node object.

        :param context: Security context
        :param node_id: the id *or* uuid of a node.
        :returns: a :class:`Node` object.
        """
        if strutils.is_int_like(node_id):
            return cls.get_by_id(context, node_id)
        elif uuidutils.is_uuid_like(node_id):
            return cls.get_by_uuid(context, node_id)
        else:
            raise exception.InvalidIdentity(identity=node_id)

    # NOTE(xek): We don't want to enable RPC on this call just yet. Remotable
    # methods can be used in the future to replace current explicit RPC calls.
    # Implications of calling new remote procedures should be thought through.
    # @object_base.remotable_classmethod
    @classmethod
    def get_by_id(cls, context, node_id):
        """Find a node based on its integer ID and return a Node object.

        :param cls: the :class:`Node`
        :param context: Security context
        :param node_id: the ID of a node.
        :returns: a :class:`Node` object.
        """
        db_node = cls.dbapi.get_node_by_id(node_id)
        node = cls._from_db_object(context, cls(), db_node)
        return node

    # NOTE(xek): We don't want to enable RPC on this call just yet. Remotable
    # methods can be used in the future to replace current explicit RPC calls.
    # Implications of calling new remote procedures should be thought through.
    # @object_base.remotable_classmethod
    @classmethod
    def get_by_uuid(cls, context, uuid):
        """Find a node based on UUID and return a Node object.

        :param cls: the :class:`Node`
        :param context: Security context
        :param uuid: the UUID of a node.
        :returns: a :class:`Node` object.
        """
        db_node = cls.dbapi.get_node_by_uuid(uuid)
        node = cls._from_db_object(context, cls(), db_node)
        return node

    # NOTE(xek): We don't want to enable RPC on this call just yet. Remotable
    # methods can be used in the future to replace current explicit RPC calls.
    # Implications of calling new remote procedures should be thought through.
    # @object_base.remotable_classmethod
    @classmethod
    def get_by_name(cls, context, name):
        """Find a node based on name and return a Node object.

        :param cls: the :class:`Node`
        :param context: Security context
        :param name: the logical name of a node.
        :returns: a :class:`Node` object.
        """
        db_node = cls.dbapi.get_node_by_name(name)
        node = cls._from_db_object(context, cls(), db_node)
        return node

    # NOTE(xek): We don't want to enable RPC on this call just yet. Remotable
    # methods can be used in the future to replace current explicit RPC calls.
    # Implications of calling new remote procedures should be thought through.
    # @object_base.remotable_classmethod
    @classmethod
    def get_by_instance_uuid(cls, context, instance_uuid):
        """Find a node based on the instance UUID and return a Node object.

        :param cls: the :class:`Node`
        :param context: Security context
        :param uuid: the UUID of the instance.
        :returns: a :class:`Node` object.
        """
        db_node = cls.dbapi.get_node_by_instance(instance_uuid)
        node = cls._from_db_object(context, cls(), db_node)
        return node

    # NOTE(xek): We don't want to enable RPC on this call just yet. Remotable
    # methods can be used in the future to replace current explicit RPC calls.
    # Implications of calling new remote procedures should be thought through.
    # @object_base.remotable_classmethod
    @classmethod
    def list(cls, context, limit=None, marker=None, sort_key=None,
             sort_dir=None, filters=None):
        """Return a list of Node objects.

        :param cls: the :class:`Node`
        :param context: Security context.
        :param limit: maximum number of resources to return in a single result.
        :param marker: pagination marker for large data sets.
        :param sort_key: column to sort results by.
        :param sort_dir: direction to sort. "asc" or "desc".
        :param filters: Filters to apply.
        :returns: a list of :class:`Node` object.

        """
        db_nodes = cls.dbapi.get_node_list(filters=filters, limit=limit,
                                           marker=marker, sort_key=sort_key,
                                           sort_dir=sort_dir)
        return cls._from_db_object_list(context, db_nodes)

    # NOTE(xek): We don't want to enable RPC on this call just yet. Remotable
    # methods can be used in the future to replace current explicit RPC calls.
    # Implications of calling new remote procedures should be thought through.
    # @object_base.remotable_classmethod
    @classmethod
    def reserve(cls, context, tag, node_id):
        """Get and reserve a node.

        To prevent other ManagerServices from manipulating the given
        Node while a Task is performed, mark it reserved by this host.

        :param cls: the :class:`Node`
        :param context: Security context.
        :param tag: A string uniquely identifying the reservation holder.
        :param node_id: A node ID or UUID.
        :raises: NodeNotFound if the node is not found.
        :returns: a :class:`Node` object.

        """
        db_node = cls.dbapi.reserve_node(tag, node_id)
        node = cls._from_db_object(context, cls(), db_node)
        return node

    # NOTE(xek): We don't want to enable RPC on this call just yet. Remotable
    # methods can be used in the future to replace current explicit RPC calls.
    # Implications of calling new remote procedures should be thought through.
    # @object_base.remotable_classmethod
    @classmethod
    def release(cls, context, tag, node_id):
        """Release the reservation on a node.

        :param context: Security context.
        :param tag: A string uniquely identifying the reservation holder.
        :param node_id: A node id or uuid.
        :raises: NodeNotFound if the node is not found.

        """
        cls.dbapi.release_node(tag, node_id)

    # NOTE(xek): We don't want to enable RPC on this call just yet. Remotable
    # methods can be used in the future to replace current explicit RPC calls.
    # Implications of calling new remote procedures should be thought through.
    # @object_base.remotable
    def create(self, context=None):
        """Create a Node record in the DB.

        Column-wise updates will be made based on the result of
        self.what_changed(). If target_power_state is provided,
        it will be checked against the in-database copy of the
        node before updates are made.

        :param context: Security context. NOTE: This should only
                        be used internally by the indirection_api.
                        Unfortunately, RPC requires context as the first
                        argument, even though we don't use it.
                        A context should be set when instantiating the
                        object, e.g.: Node(context)
        :raises: InvalidParameterValue if some property values are invalid.
        """
        values = self.do_version_changes_for_db()
        self._validate_property_values(values.get('properties'))
        self._validate_and_remove_traits(values)
        db_node = self.dbapi.create_node(values)
        self._from_db_object(self._context, self, db_node)

    # NOTE(xek): We don't want to enable RPC on this call just yet. Remotable
    # methods can be used in the future to replace current explicit RPC calls.
    # Implications of calling new remote procedures should be thought through.
    # @object_base.remotable
    def destroy(self, context=None):
        """Delete the Node from the DB.

        :param context: Security context. NOTE: This should only
                        be used internally by the indirection_api.
                        Unfortunately, RPC requires context as the first
                        argument, even though we don't use it.
                        A context should be set when instantiating the
                        object, e.g.: Node(context)
        """
        self.dbapi.destroy_node(self.uuid)
        self.obj_reset_changes()

    # NOTE(xek): We don't want to enable RPC on this call just yet. Remotable
    # methods can be used in the future to replace current explicit RPC calls.
    # Implications of calling new remote procedures should be thought through.
    # @object_base.remotable
    def save(self, context=None):
        """Save updates to this Node.

        Column-wise updates will be made based on the result of
        self.what_changed(). If target_power_state is provided,
        it will be checked against the in-database copy of the
        node before updates are made.

        :param context: Security context. NOTE: This should only
                        be used internally by the indirection_api.
                        Unfortunately, RPC requires context as the first
                        argument, even though we don't use it.
                        A context should be set when instantiating the
                        object, e.g.: Node(context)
        :raises: InvalidParameterValue if some property values are invalid.
        """
        updates = self.do_version_changes_for_db()
        self._validate_property_values(updates.get('properties'))
        if 'driver' in updates and 'driver_internal_info' not in updates:
            # Clean driver_internal_info when changes driver
            self.driver_internal_info = {}
            updates = self.do_version_changes_for_db()
        self._validate_and_remove_traits(updates)
        db_node = self.dbapi.update_node(self.uuid, updates)
        self._from_db_object(self._context, self, db_node)

    @staticmethod
    def _validate_and_remove_traits(fields):
        """Validate traits in fields for create or update, remove if present.

        :param fields: a dict of Node fields for create or update.
        :raises: BadRequest if fields contains a traits that are not None.
        """
        if 'traits' in fields:
            # NOTE(mgoddard): Traits should be updated via the node
            # object's traits field, which is itself an object. We shouldn't
            # get here with changes to traits, as this should be handled by the
            # API. When services are pinned to Pike, we can get here with
            # traits set to None in updates, due to changes made to the object
            # in _convert_to_version.
            if fields['traits']:
                # NOTE(mgoddard): We shouldn't get here as this should be
                # handled by the API.
                raise exception.BadRequest()
            fields.pop('traits')

    # NOTE(xek): We don't want to enable RPC on this call just yet. Remotable
    # methods can be used in the future to replace current explicit RPC calls.
    # Implications of calling new remote procedures should be thought through.
    # @object_base.remotable
    def refresh(self, context=None):
        """Refresh the object by re-fetching from the DB.

        :param context: Security context. NOTE: This should only
                        be used internally by the indirection_api.
                        Unfortunately, RPC requires context as the first
                        argument, even though we don't use it.
                        A context should be set when instantiating the
                        object, e.g.: Node(context)
        """
        current = self.get_by_uuid(self._context, self.uuid)
        self.obj_refresh(current)
        self.obj_reset_changes()

    # NOTE(xek): We don't want to enable RPC on this call just yet. Remotable
    # methods can be used in the future to replace current explicit RPC calls.
    # Implications of calling new remote procedures should be thought through.
    # @object_base.remotable
    def touch_provisioning(self, context=None):
        """Touch the database record to mark the provisioning as alive."""
        self.dbapi.touch_node_provisioning(self.id)

    @classmethod
    def get_by_port_addresses(cls, context, addresses):
        """Get a node by associated port addresses.

        :param cls: the :class:`Node`
        :param context: Security context.
        :param addresses: A list of port addresses.
        :raises: NodeNotFound if the node is not found.
        :returns: a :class:`Node` object.
        """
        db_node = cls.dbapi.get_node_by_port_addresses(addresses)
        node = cls._from_db_object(context, cls(), db_node)
        return node

    def _convert_fault_field(self, target_version,
                             remove_unavailable_fields=True):
        fault_is_set = self.obj_attr_is_set('fault')
        if target_version >= (1, 25):
            if not fault_is_set:
                self.fault = None
        elif fault_is_set:
            if remove_unavailable_fields:
                delattr(self, 'fault')
            elif self.fault is not None:
                self.fault = None

    def _convert_to_version(self, target_version,
                            remove_unavailable_fields=True):
        """Convert to the target version.

        Convert the object to the target version. The target version may be
        the same, older, or newer than the version of the object. This is
        used for DB interactions as well as for serialization/deserialization.

        Version 1.22: rescue_interface field was added. Its default value is
            None. For versions prior to this, it should be set to None (or
            removed).
        Version 1.23: traits field was added. Its default value is
            None. For versions prior to this, it should be set to None (or
            removed).
        Version 1.24: bios_interface field was added. Its default value is
            None. For versions prior to this, it should be set to None (or
            removed).
        Version 1.25: fault field was added. For versions prior to
            this, it should be removed.

        :param target_version: the desired version of the object
        :param remove_unavailable_fields: True to remove fields that are
            unavailable in the target version; set this to True when
            (de)serializing. False to set the unavailable fields to appropriate
            values; set this to False for DB interactions.
        """
        target_version = versionutils.convert_version_to_tuple(target_version)
        # Convert the rescue_interface field.
        rescue_iface_is_set = self.obj_attr_is_set('rescue_interface')
        if target_version >= (1, 22):
            # Target version supports rescue_interface.
            if not rescue_iface_is_set:
                # Set it to its default value if it is not set.
                self.rescue_interface = None
        elif rescue_iface_is_set:
            # Target version does not support rescue_interface, and it is set.
            if remove_unavailable_fields:
                # (De)serialising: remove unavailable fields.
                delattr(self, 'rescue_interface')
            elif self.rescue_interface is not None:
                # DB: set unavailable field to the default of None.
                self.rescue_interface = None

        traits_is_set = self.obj_attr_is_set('traits')
        if target_version >= (1, 23):
            # Target version supports traits.
            if not traits_is_set:
                self.traits = None
        elif traits_is_set:
            if remove_unavailable_fields:
                delattr(self, 'traits')
            elif self.traits is not None:
                self.traits = None

        bios_iface_is_set = self.obj_attr_is_set('bios_interface')
        if target_version >= (1, 24):
            # Target version supports bios_interface.
            if not bios_iface_is_set:
                # Set it to its default value if it is not set.
                self.bios_interface = None
        elif bios_iface_is_set:
            # Target version does not support bios_interface, and it is set.
            if remove_unavailable_fields:
                # (De)serialising: remove unavailable fields.
                delattr(self, 'bios_interface')
            elif self.bios_interface is not None:
                # DB: set unavailable field to the default of None.
                self.bios_interface = None

        self._convert_fault_field(target_version, remove_unavailable_fields)


@base.IronicObjectRegistry.register
class NodePayload(notification.NotificationPayloadBase):
    """Base class used for all notification payloads about a Node object."""
    # NOTE: This payload does not include the Node fields "chassis_id",
    # "driver_info", "driver_internal_info", "instance_info", "raid_config",
    # "reservation", or "target_raid_config". These were excluded for reasons
    # including:
    # - increased complexity needed for creating the payload
    # - sensitive information in the fields that shouldn't be exposed to
    #   external services
    # - being internal-only or hardware-related fields
    SCHEMA = {
        'clean_step': ('node', 'clean_step'),
        'console_enabled': ('node', 'console_enabled'),
        'created_at': ('node', 'created_at'),
        'driver': ('node', 'driver'),
        'extra': ('node', 'extra'),
        'inspection_finished_at': ('node', 'inspection_finished_at'),
        'inspection_started_at': ('node', 'inspection_started_at'),
        'instance_uuid': ('node', 'instance_uuid'),
        'last_error': ('node', 'last_error'),
        'maintenance': ('node', 'maintenance'),
        'maintenance_reason': ('node', 'maintenance_reason'),
        'fault': ('node', 'fault'),
        'name': ('node', 'name'),
        'bios_interface': ('node', 'bios_interface'),
        'boot_interface': ('node', 'boot_interface'),
        'console_interface': ('node', 'console_interface'),
        'deploy_interface': ('node', 'deploy_interface'),
        'inspect_interface': ('node', 'inspect_interface'),
        'management_interface': ('node', 'management_interface'),
        'network_interface': ('node', 'network_interface'),
        'power_interface': ('node', 'power_interface'),
        'raid_interface': ('node', 'raid_interface'),
        'rescue_interface': ('node', 'rescue_interface'),
        'storage_interface': ('node', 'storage_interface'),
        'vendor_interface': ('node', 'vendor_interface'),
        'power_state': ('node', 'power_state'),
        'properties': ('node', 'properties'),
        'provision_state': ('node', 'provision_state'),
        'provision_updated_at': ('node', 'provision_updated_at'),
        'resource_class': ('node', 'resource_class'),
        'target_power_state': ('node', 'target_power_state'),
        'target_provision_state': ('node', 'target_provision_state'),
        'updated_at': ('node', 'updated_at'),
        'uuid': ('node', 'uuid')
    }

    # Version 1.0: Initial version, based off of Node version 1.18.
    # Version 1.1: Type of network_interface changed to just nullable string
    #              similar to version 1.20 of Node.
    # Version 1.2: Add nullable to console_enabled and maintenance.
    # Version 1.3: Add dynamic interfaces fields exposed via API.
    # Version 1.4: Add storage interface field exposed via API.
    # Version 1.5: Add rescue interface field exposed via API.
    # Version 1.6: Add traits field exposed via API.
    # Version 1.7: Add fault field exposed via API.
    # Version 1.8: Add bios interface field exposed via API.
    VERSION = '1.8'
    fields = {
        'clean_step': object_fields.FlexibleDictField(nullable=True),
        'console_enabled': object_fields.BooleanField(nullable=True),
        'created_at': object_fields.DateTimeField(nullable=True),
        'driver': object_fields.StringField(nullable=True),
        'extra': object_fields.FlexibleDictField(nullable=True),
        'inspection_finished_at': object_fields.DateTimeField(nullable=True),
        'inspection_started_at': object_fields.DateTimeField(nullable=True),
        'instance_uuid': object_fields.UUIDField(nullable=True),
        'last_error': object_fields.StringField(nullable=True),
        'maintenance': object_fields.BooleanField(nullable=True),
        'maintenance_reason': object_fields.StringField(nullable=True),
        'fault': object_fields.StringField(nullable=True),
        'bios_interface': object_fields.StringField(nullable=True),
        'boot_interface': object_fields.StringField(nullable=True),
        'console_interface': object_fields.StringField(nullable=True),
        'deploy_interface': object_fields.StringField(nullable=True),
        'inspect_interface': object_fields.StringField(nullable=True),
        'management_interface': object_fields.StringField(nullable=True),
        'network_interface': object_fields.StringField(nullable=True),
        'power_interface': object_fields.StringField(nullable=True),
        'raid_interface': object_fields.StringField(nullable=True),
        'rescue_interface': object_fields.StringField(nullable=True),
        'storage_interface': object_fields.StringField(nullable=True),
        'vendor_interface': object_fields.StringField(nullable=True),
        'name': object_fields.StringField(nullable=True),
        'power_state': object_fields.StringField(nullable=True),
        'properties': object_fields.FlexibleDictField(nullable=True),
        'provision_state': object_fields.StringField(nullable=True),
        'provision_updated_at': object_fields.DateTimeField(nullable=True),
        'resource_class': object_fields.StringField(nullable=True),
        'target_power_state': object_fields.StringField(nullable=True),
        'target_provision_state': object_fields.StringField(nullable=True),
        'traits': object_fields.ListOfStringsField(nullable=True),
        'updated_at': object_fields.DateTimeField(nullable=True),
        'uuid': object_fields.UUIDField()
    }

    def __init__(self, node, **kwargs):
        super(NodePayload, self).__init__(**kwargs)
        self.populate_schema(node=node)
        # NOTE(mgoddard): Populate traits with a list of trait names, rather
        # than the TraitList object.
        if node.obj_attr_is_set('traits') and node.traits is not None:
            self.traits = node.traits.get_trait_names()
        else:
            self.traits = []


@base.IronicObjectRegistry.register
class NodeSetPowerStateNotification(notification.NotificationBase):
    """Notification emitted when ironic changes a node's power state."""
    # Version 1.0: Initial version
    VERSION = '1.0'

    fields = {
        'payload': object_fields.ObjectField('NodeSetPowerStatePayload')
    }


@base.IronicObjectRegistry.register
class NodeSetPowerStatePayload(NodePayload):
    """Payload schema for when ironic changes a node's power state."""
    # Version 1.0: Initial version
    # Version 1.1: Parent NodePayload version 1.1
    # Version 1.2: Parent NodePayload version 1.2
    # Version 1.3: Parent NodePayload version 1.3
    # Version 1.4: Parent NodePayload version 1.4
    # Version 1.5: Parent NodePayload version 1.5
    # Version 1.6: Parent NodePayload version 1.6
    # Version 1.7: Parent NodePayload version 1.7
    # Version 1.8: Parent NodePayload version 1.8
    VERSION = '1.8'

    fields = {
        # "to_power" indicates the future target_power_state of the node. A
        # separate field from target_power_state is used so that the
        # baremetal.node.power_set.start notification, which is sent before
        # target_power_state is set on the node, has information about what
        # state the conductor will attempt to set on the node.
        'to_power': object_fields.StringField(nullable=True)
    }

    def __init__(self, node, to_power):
        super(NodeSetPowerStatePayload, self).__init__(
            node, to_power=to_power)


@base.IronicObjectRegistry.register
class NodeCorrectedPowerStateNotification(notification.NotificationBase):
    """Notification for when a node's power state is corrected in the database.

       This notification is emitted when ironic detects that the actual power
       state on a bare metal hardware is different from the power state on an
       ironic node (DB). This notification is emitted after the database is
       updated to reflect this correction.
    """
    # Version 1.0: Initial version
    VERSION = '1.0'

    fields = {
        'payload': object_fields.ObjectField('NodeCorrectedPowerStatePayload')
    }


@base.IronicObjectRegistry.register
class NodeCorrectedPowerStatePayload(NodePayload):
    """Notification payload schema for when a node's power state is corrected.

       "from_power" indicates the previous power state on the ironic node
       before the node was updated.
    """
    # Version 1.0: Initial version
    # Version 1.1: Parent NodePayload version 1.1
    # Version 1.2: Parent NodePayload version 1.2
    # Version 1.3: Parent NodePayload version 1.3
    # Version 1.4: Parent NodePayload version 1.4
    # Version 1.5: Parent NodePayload version 1.5
    # Version 1.6: Parent NodePayload version 1.6
    # Version 1.7: Parent NodePayload version 1.7
    # Version 1.8: Parent NodePayload version 1.8
    VERSION = '1.8'

    fields = {
        'from_power': object_fields.StringField(nullable=True)
    }

    def __init__(self, node, from_power):
        super(NodeCorrectedPowerStatePayload, self).__init__(
            node, from_power=from_power)


@base.IronicObjectRegistry.register
class NodeSetProvisionStateNotification(notification.NotificationBase):
    """Notification emitted when ironic changes a node provision state."""
    # Version 1.0: Initial version
    VERSION = '1.0'

    fields = {
        'payload': object_fields.ObjectField('NodeSetProvisionStatePayload')
    }


@base.IronicObjectRegistry.register
class NodeSetProvisionStatePayload(NodePayload):
    """Payload schema for when ironic changes a node provision state."""
    # Version 1.0: Initial version
    # Version 1.1: Parent NodePayload version 1.1
    # Version 1.2: Parent NodePayload version 1.2
    # Version 1.3: Parent NodePayload version 1.3
    # Version 1.4: Parent NodePayload version 1.4
    # Version 1.6: Parent NodePayload version 1.6
    # Version 1.7: Parent NodePayload version 1.7
    # Version 1.8: Parent NodePayload version 1.8
    VERSION = '1.8'

    SCHEMA = dict(NodePayload.SCHEMA,
                  **{'instance_info': ('node', 'instance_info')})

    fields = {
        'instance_info': object_fields.FlexibleDictField(nullable=True),
        'event': object_fields.StringField(nullable=True),
        'previous_provision_state': object_fields.StringField(nullable=True),
        'previous_target_provision_state':
            object_fields.StringField(nullable=True)
    }

    def __init__(self, node, prev_state, prev_target, event):
        super(NodeSetProvisionStatePayload, self).__init__(
            node, event=event, previous_provision_state=prev_state,
            previous_target_provision_state=prev_target)


@base.IronicObjectRegistry.register
class NodeCRUDNotification(notification.NotificationBase):
    """Notification emitted when ironic creates, updates or deletes a node."""
    # Version 1.0: Initial version
    VERSION = '1.0'

    fields = {
        'payload': object_fields.ObjectField('NodeCRUDPayload')
    }


@base.IronicObjectRegistry.register
class NodeCRUDPayload(NodePayload):
    """Payload schema for when ironic creates, updates or deletes a node."""
    # Version 1.0: Initial version
    # Version 1.1: Parent NodePayload version 1.3
    # Version 1.2: Parent NodePayload version 1.4
    # Version 1.3: Parent NodePayload version 1.5
    # Version 1.4: Parent NodePayload version 1.6
    # Version 1.5: Parent NodePayload version 1.7
    # Version 1.6: Parent NodePayload version 1.8
    VERSION = '1.6'

    SCHEMA = dict(NodePayload.SCHEMA,
                  **{'instance_info': ('node', 'instance_info'),
                     'driver_info': ('node', 'driver_info')})

    fields = {
        'chassis_uuid': object_fields.UUIDField(nullable=True),
        'instance_info': object_fields.FlexibleDictField(nullable=True),
        'driver_info': object_fields.FlexibleDictField(nullable=True)
    }

    def __init__(self, node, chassis_uuid):
        super(NodeCRUDPayload, self).__init__(node, chassis_uuid=chassis_uuid)


@base.IronicObjectRegistry.register
class NodeMaintenanceNotification(notification.NotificationBase):
    """Notification emitted when maintenance state changed via API."""
    # Version 1.0: Initial version
    VERSION = '1.0'

    fields = {
        'payload': object_fields.ObjectField('NodePayload')
    }


@base.IronicObjectRegistry.register
class NodeConsoleNotification(notification.NotificationBase):
    """Notification emitted when node console state changed."""
    # Version 1.0: Initial version
    VERSION = '1.0'

    fields = {
        'payload': object_fields.ObjectField('NodePayload')
    }
