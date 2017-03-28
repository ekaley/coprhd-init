CoprHD-init
=====

This python script is to initialize CoprHD for VxRack services. It takes the following actions sequentially

  1. Mark completion of CoprHD initial configuration wizard
  2. Cleanup stale records so that this script is reentrant
  3. Upload Ansible playbook file
  4. Create workflow
  5. Create catalog category and services

This script is re-entrant. It removes all VxRack related workflow, ansible package, catalog
services before creating new.

