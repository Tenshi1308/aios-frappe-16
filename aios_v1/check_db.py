import sys
sys.path.insert(0, '/home/samue/mybench/apps/aios_v1')
import frappe

def main():
    frappe.init(site='aios.localhost', sites_path='/home/samue/mybench/sites')
    frappe.connect()
    tenants = frappe.get_all('AIOS Tenant', fields=['name', 'tenant_name', 'role', 'status'])
    convs = frappe.get_all('AIOS Conversation', fields=['name', 'tenant', 'branch', 'title'])
    mapping = frappe.get_all('AIOS Mapping', fields=['name', 'connection', 'status'])
    entries = frappe.get_all('AIOS Mapping Entry', fields=['name', 'mapping', 'canonical_entity', 'canonical_field', 'source_table', 'source_column'])
    print("=== MAPPINGS ===", mapping)
    print("=== TOTAL ENTRIES ===", len(entries))
    tables = sorted(list(set(e.source_table for e in entries)))
    print("=== SOURCE TABLES IN ENTRIES ===", tables)

if __name__ == '__main__':
    main()
