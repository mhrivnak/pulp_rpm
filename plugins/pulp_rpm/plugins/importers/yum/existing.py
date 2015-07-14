import logging
import os

from pulp.plugins.loader import api as plugin_api
from pulp.plugins.util.misc import paginate
from pulp.server.controllers import repository as repo_controller
from pulp.server.controllers import units as units_controller
from pulp.server.db.model.criteria import Criteria, UnitAssociationCriteria

from pulp_rpm.common import ids


_LOGGER = logging.getLogger(__name__)


def check_repo(wanted):
    """
    Given an iterable of units as namedtuples, this function will search for them
    using the given search method and return the set of tuples that were not
    found. This checks for the unit in the db as well as for the actual file
    on the filesystem. Note that the check for the actual file is performed only
    for the supported unit types.

    This is useful in a case where you know what units you want to have in a repo,
    but need to know which you need to actually download by eliminating the ones
    you already have.

    :param wanted:          iterable of units as namedtuples
    :type  wanted:          iterable
    :param sync_conduit:
    :type  sync_conduit:    pulp.plugins.conduits.repo_sync.RepoSyncConduit

    :return:    set of unit keys as namedtuples, identifying which of the
                named tuples received as input were not found by the
                search method.
    :rtype:     set
    """
    # sort by type
    sorted_units = _sort_by_type(wanted)
    # UAQ for each type
    for unit_type, values in sorted_units.iteritems():
        model = plugin_api.get_unit_model_by_id(unit_type)

        fields = model.unit_key_fields + ('_storage_path',)
        rpm_srpm_drpm = unit_type in (ids.TYPE_ID_RPM,
                                      ids.TYPE_ID_SRPM,
                                      ids.TYPE_ID_DRPM)

        unit_generator = (model(**unit_tuple._asdict()) for unit_tuple in values)
        for unit in units_controller.find_units(unit_generator, fields=fields):
            if rpm_srpm_drpm:
                # For RPMs, SRPMs and DRPMs, also check if the file exists on the filesystem.
                # If not, we do not want to skip downloading the unit.
                if unit.storage_path is None or not os.path.isfile(unit.storage_path):
                    continue
            values.discard(unit.unit_key_as_named_tuple)

    ret = set()
    ret.update(*sorted_units.values())
    return ret


def get_existing_units(search_dicts, unit_fields, unit_type, search_method):
    """

    :param search_dicts:
    :param unit_fields:
    :param unit_type:
    :param search_method:
    :return:    generator of Units
    """
    for segment in paginate(search_dicts):
        unit_filters = {'$or': list(segment)}
        criteria = UnitAssociationCriteria([unit_type], unit_filters=unit_filters,
                                           unit_fields=unit_fields, association_fields=[])
        for result in search_method(criteria):
            yield result


def check_all_and_associate(wanted, sync_conduit):
    """
    Given a set of unit keys as namedtuples, this function checks if a unit
    already exists in Pulp and returns the set of tuples that were not
    found. This checks for the unit in the db as well as for the actual file
    on the filesystem. If a unit exists in the db and the filesystem, this function
    also associates the unit to the given repo. Note that the check for the actual file
    is performed only for the supported unit types.

    :param wanted:          iterable of units as namedtuples
    :type  wanted:          iterable
    :param sync_conduit:    repo sync conduit
    :type  sync_conduit:    pulp.plugins.conduits.repo_sync.RepoSync

    :return:    set of unit keys as namedtuples, identifying which of the
                named tuples received as input were not found on the server.
    :rtype:     set
    """
    sorted_units = _sort_by_type(wanted)
    for unit_type, values in sorted_units.iteritems():
        model = plugin_api.get_unit_model_by_id(unit_type)
        fields = model.unit_key_fields + ('storage_path',)
        rpm_srpm_drpm = unit_type in (ids.TYPE_ID_RPM,
                                      ids.TYPE_ID_SRPM,
                                      ids.TYPE_ID_DRPM)

        unit_generator = (model(**unit_tuple._asdict()) for unit_tuple in values)
        for unit in units_controller.find_units(unit_generator, fields=fields):
            if rpm_srpm_drpm:
                # For RPMs, SRPMs and DRPMs, also check if the file exists on the filesystem.
                # If not, we do not want to skip downloading the unit.
                if unit.storage_path is None or not os.path.isfile(unit.storage_path):
                    continue
            # Add the existing unit to the repository
            repo_controller.associate_single_unit(sync_conduit.repo, unit)
            values.discard(unit.unit_key_as_named_tuple)

    ret = set()
    ret.update(*sorted_units.values())
    return ret


def _sort_by_type(wanted):
    ret = {}
    for unit in wanted:
        ret.setdefault(unit.__class__.__name__, set()).add(unit)
    return ret
