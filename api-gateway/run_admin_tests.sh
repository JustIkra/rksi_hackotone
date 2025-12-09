#!/bin/bash
# Script to run the admin tests with proper environment variables

export FILE_STORAGE_BASE=/tmp/test_storage
export POSTGRES_DSN_TEST="postgresql+asyncpg://app:app@127.0.0.1:5432/app"
export ENV=test
export JWT_SECRET=test_secret_key_for_testing_only

echo "Running updated admin tests..."
echo "================================"
echo ""

echo "Test 1: test_revoke_admin_role_from_self_forbidden"
echo "Expected: 200 OK (cross-user operation)"
python3 -m pytest tests/test_admin.py::test_revoke_admin_role_from_self_forbidden -v --tb=short
echo ""

echo "Test 2: test_delete_user_self_forbidden"
echo "Expected: 200 OK (cross-user operation)"
python3 -m pytest tests/test_admin.py::test_delete_user_self_forbidden -v --tb=short
echo ""

echo "Test 3: test_revoke_admin_role_from_actual_self_forbidden"
echo "Expected: 400 Bad Request (proper self-revocation prevention)"
python3 -m pytest tests/test_admin.py::test_revoke_admin_role_from_actual_self_forbidden -v --tb=short
echo ""

echo "Test 4: test_delete_actual_self_forbidden"
echo "Expected: 400 Bad Request (proper self-deletion prevention)"
python3 -m pytest tests/test_admin.py::test_delete_actual_self_forbidden -v --tb=short
echo ""

echo "Running all admin tests..."
python3 -m pytest tests/test_admin.py -v
