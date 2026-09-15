"""All-scope consent across actual process exit and a fresh interpreter."""
import pytest
from test_project_archive_delete_process import run_delete_process_case


@pytest.mark.parametrize('case', [
    'capture','partial','facts_deleted','effect','prepared','core_restored',
    'cleanup_bundle','cleanup_journal','cleanup_replaced','cleanup_journal_unlinked',
    'core_restored_rebuild_session','prepared_changed_messages',
])
def test_all_archive_delete_real_process_recovery(case):
    run_delete_process_case(case, all_scope=True)
