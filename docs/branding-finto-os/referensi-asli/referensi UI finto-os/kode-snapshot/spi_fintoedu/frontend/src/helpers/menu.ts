import {
  ADMINISTRATOR_MENU_ITEMS,
  UNASSIGNED_MENU_ITEMS,
  createRoleMenu,
} from "@/assets/data/menu-items";
import type { RoleProfile } from "@/types/auth";
import type { MenuItemType } from "@/types/menu";

/** Hanya user "Administrator" yang dianggap Super Administrator (boleh membuka Desk /app & "Lihat sebagai"). */
export const SUPER_ADMINISTRATOR = "Administrator";

/** Menu khusus user Administrator (System Manager lain tidak melihatnya): Desk, Monitoring Aktivitas, Session Replay. */
const SUPER_ADMINISTRATOR_ONLY_KEYS = new Set([
  "administrator-desk",
  "administrator-activity-monitor",
  "administrator-session-replay",
]);

export type MenuUserContext = {
  roleProfile: RoleProfile | null;
  isSystemManager: boolean;
  username?: string | null;
  /** Role pilihan Super Administrator ("Lihat sebagai"). */
  viewAsRole?: RoleProfile | null;
  employmentCategory?: string | null;
};

export const getMenuItems = (ctx: MenuUserContext): MenuItemType[] => {
  const isSuperAdministrator = ctx.username === SUPER_ADMINISTRATOR;
  if (isSuperAdministrator && ctx.viewAsRole) {
    return createRoleMenu(ctx.viewAsRole);
  }
  if (ctx.isSystemManager) {
    return isSuperAdministrator
      ? ADMINISTRATOR_MENU_ITEMS
      : ADMINISTRATOR_MENU_ITEMS.filter((item) => !SUPER_ADMINISTRATOR_ONLY_KEYS.has(item.key));
  }
  if (ctx.roleProfile) {
    return createRoleMenu(ctx.roleProfile, { employmentCategory: ctx.employmentCategory ?? null });
  }
  return UNASSIGNED_MENU_ITEMS;
};

export const findAllParent = (
  menuItems: MenuItemType[],
  menuItem: MenuItemType,
): string[] => {
  let parents: string[] = [];
  const parent = findMenuItem(menuItems, menuItem.parentKey);
  if (parent) {
    parents.push(parent.key);
    if (parent.parentKey) {
      parents = [...parents, ...findAllParent(menuItems, parent)];
    }
  }
  return parents;
};

export const getMenuItemFromURL = (
  items: MenuItemType | MenuItemType[],
  url: string,
): MenuItemType | undefined => {
  if (items instanceof Array) {
    for (const item of items) {
      const foundItem = getMenuItemFromURL(item, url);
      if (foundItem) {
        return foundItem;
      }
    }
  } else {
    if (items.url == url) return items;
    if (items.children != null) {
      for (const item of items.children) {
        if (item.url == url) return item;
      }
    }
  }
};

export const findMenuItem = (
  menuItems: MenuItemType[] | undefined,
  menuItemKey: MenuItemType["key"] | undefined,
): MenuItemType | null => {
  if (menuItems && menuItemKey) {
    for (const item of menuItems) {
      if (item.key === menuItemKey) {
        return item;
      }
      const found = findMenuItem(item.children, menuItemKey);
      if (found) return found;
    }
  }
  return null;
};
