# Audit log sample (Assignment 2)

| Time | Actor | Action | Target student | Decision | Approval status | Result | Detail |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-11-02T17:59:12 | STAFF01 (staff) | login | STAFF01 | allowed | not_required | success |  |
| 2026-11-02T17:59:12 | S1001 (student) | login | S1001 | allowed | not_required | success |  |
| 2026-11-02T17:59:13 | S1001 (student) | get_fee_status | S1001 | allowed | not_required | success |  |
| 2026-11-02T17:59:24 | S1001 (student) | login | S1001 | allowed | not_required | success |  |
| 2026-11-02T17:59:35 | S1004 (student) | login | S1004 | allowed | not_required | success |  |
| 2026-11-02T17:59:39 | S1004 (student) | remember_fact | S1004 | allowed | not_required | success |  |
| 2026-11-02T17:59:39 | S1004 (student) | remember_fact | S1004 | allowed | not_required | success |  |
| 2026-11-02T17:59:50 | S1004 (student) | login | S1004 | allowed | not_required | success |  |
| 2026-11-02T18:00:00 | S1002 (student) | login | S1002 | allowed | not_required | success |  |
| 2026-11-02T18:00:00 | S1002 (student) | sensitive_input_removed | S1002 | allowed | not_required | success | Removed from chat before processing: otp |
| 2026-11-02T18:00:11 | S1003 (student) | login | S1003 | allowed | not_required | success |  |
| 2026-11-02T18:00:23 | S1001 (student) | login | S1001 | allowed | not_required | success |  |
| 2026-11-02T18:00:35 | S1001 (student) | login | S1001 | allowed | not_required | success |  |
| 2026-11-02T18:00:36 | S1001 (student) | get_scholarship_status | S1001 | allowed | not_required | success |  |
| 2026-11-02T18:00:48 | S1001 (student) | login | S1001 | allowed | not_required | success |  |
| 2026-11-02T18:00:59 | S1001 (student) | login | S1001 | allowed | not_required | success |  |
| 2026-11-02T18:01:00 | S1001 (student) | create_support_request | S1001 | allowed | not_required | success |  |
| 2026-11-02T18:01:11 | S1001 (student) | login | S1001 | allowed | not_required | success |  |
| 2026-11-02T18:01:26 | S1005 (student) | login | S1005 | allowed | not_required | success |  |
| 2026-11-02T18:01:26 | S1005 (student) | get_fee_status | S1005 | allowed | not_required | error:fee_record_unavailable |  |
| 2026-11-02T18:01:37 | S1001 (student) | login | S1001 | allowed | not_required | success |  |
| 2026-11-02T18:01:38 | S1001 (student) | get_fee_status | S9999 | blocked | not_required | denied | Signed-in user is not the owner of this record. |
| 2026-11-02T18:01:49 | S1003 (student) | login | S1003 | allowed | not_required | success |  |
| 2026-11-02T18:02:00 | S1001 (student) | login | S1001 | allowed | not_required | success |  |
| 2026-11-02T18:02:01 | S1001 (student) | get_student_record | S1001 | allowed | not_required | success |  |
| 2026-11-02T18:02:12 | S1001 (student) | login | S1001 | allowed | not_required | success |  |
| 2026-11-02T18:02:25 | S1001 (student) | login | S1001 | allowed | not_required | success |  |
| 2026-11-02T18:02:36 | S1001 (student) | login | S1001 | allowed | not_required | success |  |
| 2026-11-02T18:02:47 | S1001 (student) | login | S1001 | allowed | not_required | success |  |
| 2026-11-02T18:02:49 | S1001 (student) | update_contact_details | S1001 | approval_required | pending | pending_approval | Approval AP-0001 created. Nothing was changed. |
| 2026-11-02T18:02:59 | STAFF01 (staff) | update_contact_details | S1001 | allowed | approved | success | Approved AP-0001; requested by S1001. |
| 2026-11-02T18:02:59 | S1002 (student) | login | S1002 | allowed | not_required | success |  |
| 2026-11-02T18:03:00 | S1002 (student) | update_contact_details | S1002 | approval_required | pending | pending_approval | Approval AP-0002 created. Nothing was changed. |
| 2026-11-02T18:03:11 | STAFF01 (staff) | update_contact_details | S1002 | allowed | rejected | not_executed | Rejected AP-0002; requested by S1002. |
| 2026-11-02T18:03:11 | S1001 (student) | login | S1001 | allowed | not_required | success |  |
| 2026-11-02T18:03:11 | S1001 (student) | sensitive_input_removed | S1001 | allowed | not_required | success | Removed from chat before processing: password, otp |