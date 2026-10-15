# Test Plan Summary

## Plan
- Test plan ID: TP-PRC-IAM-014-2026Q1
- Process ID and name: PRC-IAM-014 — User Account Password Reset (Service Desk Assisted)
- Controls in scope: CTL-IAM-0472; CTL-IAM-0473; CTL-IAM-0474
- Control details reference: CD-PRC-IAM-014 v3.2, effective 01-Jan-2026
- Testing period: 01 January 2026 to 31 March 2026
- Test type: Operating effectiveness
- Tester: NOT STATED
- Reviewer: NOT STATED

## Sampling
| Control ID | Population source | Population size | Sample size | Selection method |
|---|---|---|---|---|
| CTL-IAM-0472 | ADX audit log extract of completed resets, reconciled to ServiceNow SD tickets | 1847 | 25 | Random, seeded KCT sampling tool; population agreed to ADX source count first |
| CTL-IAM-0473 | Same population as CTL-IAM-0472, plus tool configuration in force | 1847 | 25 | Same 25 items as CTL-IAM-0472 |
| CTL-IAM-0474 | Monthly reconciliation workbooks and approvals | 3 | 3 | Full population |

## Test steps

### CTL-IAM-0472
| Step ID | Attribute | Test procedure (condensed) | Evidence IDs | Pass criteria (thresholds intact) | Exception definition | Scope |
|---|---|---|---|---|---|---|
| 0472-01 | Verification recorded | Inspect the Identity Verification section on each sampled SD ticket | EV-01 | Section present and complete: factors, outcome, timestamp, acting agent | Section absent, blank, or missing any of the four fields | per sample |
| 0472-02 | Two factors applied | Inspect recorded factors | EV-01, EV-02 | At least two of the three approved factors recorded as successful | Fewer than two factors, or a failed/partial factor | per sample |
| 0472-03 | Approved factors only | Inspect Factor B attributes; agree Factor A to authenticator log | EV-01, EV-02 | Factor B attributes from Verify-ID, none public; Factor A in log for registered device, successful | Public attribute used, or Factor A missing from log | per sample |
| 0472-04 | Verification precedes reset | Compare verification time to ADX reset time | EV-01, EV-03 | Verification earlier than reset, same agent ID | Reset before/without verification, or different agent | per sample |
| 0472-05 | Rejected requests handled | Inspect all rejected requests and SEC incidents | EV-01, EV-04 | No reset executed; SEC raised within one hour | Reset executed, no SEC, or SEC after more than one hour | NOT STATED |

### CTL-IAM-0473
| Step ID | Attribute | Test procedure (condensed) | Evidence IDs | Pass criteria (thresholds intact) | Exception definition | Scope |
|---|---|---|---|---|---|---|
| 0473-01 | Generation parameters | Inspect tool configuration | EV-05 | Length at least 12, complexity per BL-SEC-012, no agent override | Below 12, deviating complexity, or agent-editable field | once for period |
| 0473-02 | Validity window | Inspect expiry setting, agree to sampled timestamps | EV-05, EV-03 | Configured validity at most 60 minutes; each sampled expiry at most 60 minutes after generation | Above 60 minutes configured or on any sample | once for period |
| 0473-03 | Forced change at first logon | Inspect forced-change flag | EV-03 | Flag set for every sampled account at reset | Flag not set, or removed before first logon | per sample |
| 0473-04 | Single use enforced | Inspect authentication events after issuance | EV-03 | Authenticates at most once; later attempts rejected or credential invalidated | More than one successful authentication | per sample |
| 0473-05 | Delivery channel | Agree delivery to registered mobile or manager secure link | EV-06, EV-01 | Registered mobile, or manager secure link where none; no e-mail, chat or verbal | Unregistered number, or read out / e-mail / chat | per sample |

### CTL-IAM-0474
| Step ID | Attribute | Test procedure (condensed) | Evidence IDs | Pass criteria (thresholds intact) | Exception definition | Scope |
|---|---|---|---|---|---|---|
| 0474-01 | Timeliness | Inspect completion and approval dates per month | EV-07, EV-10 | Completed and approved on or before 10th working day after month end | Later than 10th working day, or no date | per sample |
| 0474-02 | Population completeness | Agree extract count to ADX source count | EV-07, EV-03 | Counts agree, or differences explained and supported | Unexplained difference, or extract not covering full month | per sample |
| 0474-03 | Reconciliation performed | Inspect matching of reset events to tickets | EV-07 | Every event matched to an approved ticket with completed verification, or recorded as exception | Unmatched and not an exception, or matched to incomplete ticket | per sample |
| 0474-04 | Exception handling | Inspect each exception's entry, notes and closure | EV-08 | Closed within five working days; unauthorised resets escalated to CISO with SEC same working day | Open beyond five days unjustified, or escalation not same day | per sample |
| 0474-05 | Independent review | Compare approver to preparer | EV-10, EV-07 | Approved by IAM Operations Manager, not the preparer, dated on or after completion | Self-approval, wrong approver, or approval before completion | per sample |

## Evidence required
| Evidence ID | Description | Expected format | Source system | Period |
|---|---|---|---|---|
| EV-01 | ServiceNow SD ticket exports for the 25 sampled resets | PDF (one per ticket) | ServiceNow | 2026 Q1 |
| EV-02 | Mobile Authenticator push challenge log for sampled resets | XLSX | Mobile Authenticator | 2026 Q1 |
| EV-03 | ADX audit log extract of all reset events | XLSX or CSV | ADX directory | 01-Jan to 31-Mar-2026 |
| EV-04 | SEC incident ticket exports for rejected requests | PDF | ServiceNow | 2026 Q1 |
| EV-05 | ADX Password Reset Tool configuration export | PDF | ADX Password Reset Tool v4.1 | In force during 2026 Q1 |
| EV-06 | SMS gateway delivery log for sampled resets | XLSX | SMS gateway | 2026 Q1 |
| EV-07 | Monthly reconciliation workbooks | XLSX (three files) | IAM Operations SharePoint | Jan / Feb / Mar 2026 |
| EV-08 | IAM Exception Register extract | XLSX | SharePoint list | 2026 Q1 |
| EV-09 | Organisation chart or role listing for preparer and reviewer | PDF | HR system | As at 31-Mar-2026 |
| EV-10 | Reviewer approval e-mails | MSG (three files) | Outlook | Jan / Feb / Mar 2026 |

## Execution status
- Results recorded in this document: no — every result field is blank and no conclusion can be drawn from this document.
- Exceptions recorded: None (0 per control)
- Conclusion recorded: No — all controls "Not yet tested"

## Gaps in this document
- Tester
- Reviewer
- Scope of step 0472-05
