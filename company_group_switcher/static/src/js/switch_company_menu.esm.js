import {patch} from "@web/core/utils/patch";
import {session} from "@web/session";
import {user} from "@web/core/user";
import {symmetricalDifference} from "@web/core/utils/arrays";
import {
  CompanySelector,
  SwitchCompanyMenu,
} from "@web/webclient/switch_company_menu/switch_company_menu";

const lockedIds = session.company_locked_ids || false;

// Usuario sin permiso de cambio: el cliente opera siempre con las empresas
// asignadas (el servidor igualmente lo fuerza, esto evita desincronización
// con una cookie `cids` vieja o manipulada).
if (
  lockedIds &&
  symmetricalDifference(
    lockedIds,
    user.activeCompanies.map((c) => c.id)
  ).length
) {
  user.activateCompanies(lockedIds, {includeChildCompanies: false, reload: false});
}

patch(CompanySelector.prototype, {
  get companyGroups() {
    return [...(session.company_groups || [])].sort(
      (a, b) => a.sequence - b.sequence || a.name.localeCompare(b.name)
    );
  },

  get isLocked() {
    return Boolean(lockedIds);
  },

  isGroupActive(group) {
    const active = user.activeCompanies.map((c) => c.id);
    return !symmetricalDifference(group.company_ids, active).length;
  },

  switchGroup(group) {
    if (this.isLocked) {
      return;
    }
    // La primera empresa del grupo queda como empresa activa
    this.selectedCompaniesIds = [...group.company_ids];
    this.apply();
    this.dropdownState.close?.();
  },
});

patch(SwitchCompanyMenu.prototype, {
  get companyGroups() {
    return this.companySelector.companyGroups;
  },

  get activeGroup() {
    return this.companyGroups.find((g) => this.companySelector.isGroupActive(g));
  },

  get currentLabel() {
    const group = this.activeGroup;
    return group && user.activeCompanies.length > 1
      ? group.name
      : user.activeCompany.name;
  },

  get isSingleCompany() {
    return this.companySelector.isLocked || super.isSingleCompany;
  },

  get showGroups() {
    return !this.companySelector.isLocked && this.companyGroups.length > 0;
  },
});
