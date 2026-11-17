# Python CLI Alarm Clock

## 1. Problem Statement

Build a lightweight alarm clock application that runs entirely through a command-line interface (CLI).

The application should allow users to create, manage, schedule, and receive notifications for alarms. It should support multiple alarms, persist alarm configurations locally, and reliably trigger alarms at their scheduled times while the application is running.

There is no requirement for a graphical interface, web application, remote database, or external service.

---

## 2. Goals

The primary goals are:

1. Provide a simple CLI for managing alarms.
2. Support multiple independently configurable alarms.
3. Persist alarm configurations across application restarts.
4. Trigger alarms at their scheduled times.
5. Support enabling, disabling, deleting, and modifying alarms.
6. Provide alarm dismissal and snooze functionality.
7. Support recurring alarms.
8. Handle time-related edge cases reliably.
9. Maintain a modular and testable codebase.
10. Minimize external dependencies by preferring Python's standard library.

---

## 3. Functional Requirements

### FR-01: Create Alarm

Users must be able to create an alarm by specifying:

- Alarm time.
- Optional label.
- Optional recurrence configuration.
- Optional snooze duration.

Expected behaviour:

- Every alarm must have a unique identifier.
- Alarm time must be validated.
- Alarms must be enabled by default.
- Invalid configurations must be rejected with meaningful error messages.
- Successfully created alarms must be persisted.

### FR-02: List Alarms

Users must be able to view all configured alarms.

The listing should include:

- Alarm ID.
- Scheduled time.
- Label.
- Enabled/disabled status.
- Recurrence information, if applicable.
- Next scheduled occurrence.

### FR-03: Update Alarm

Users must be able to modify an existing alarm.

Supported updates:

- Scheduled time.
- Label.
- Enabled status.
- Recurrence configuration.
- Snooze duration.

Expected behaviour:

- Invalid updates must be rejected.
- Changes must be persisted.
- The scheduler must be notified when an update affects scheduling.

### FR-04: Delete Alarm

Users must be able to delete an alarm using its identifier.

Expected behaviour:

- Deleted alarms must be removed from persistent storage.
- The scheduler must no longer trigger deleted alarms.
- Deleting a nonexistent alarm must produce an appropriate error.

### FR-05: Enable and Disable Alarm

Users must be able to enable or disable individual alarms.

Expected behaviour:

- Disabled alarms must not trigger.
- Re-enabling an alarm must make it eligible for scheduling again.
- Changes must persist across application restarts.

### FR-06: Alarm Scheduling

The application must monitor enabled alarms and trigger them when their scheduled time arrives.

Expected behaviour:

- Multiple alarms must be supported.
- The scheduler must identify the next upcoming alarm.
- The scheduler should avoid unnecessary busy polling.
- The scheduler must respond to changes in alarm configurations.
- Multiple alarms scheduled for the same time must all trigger.
- A one-time alarm must not trigger repeatedly.
- The scheduler must support graceful shutdown.

Time-handling requirements:

- Use the operating system's local clock for scheduled calendar times.
- Use wall-clock time to determine whether an alarm is due.
- Use a monotonic clock for measuring elapsed waiting time where appropriate.
- Recalculate scheduling decisions when the system clock changes.
- Avoid relying exclusively on a long, uninterrupted sleep.

### FR-07: Alarm Notifications

When an alarm triggers, the application must notify the user.

Initial notification mechanisms:

- Display an alarm message in the terminal.
- Produce an audible terminal bell.

Optional enhancement:

- Support playing a locally available audio file.

Expected behaviour:

- Notification logic must be independent of scheduling logic.
- Notification failures must not crash the scheduler.
- Multiple simultaneous alarms must be handled correctly.

### FR-08: Dismiss Alarm

Users must be able to dismiss a currently ringing alarm.

Expected behaviour:

- The notification must stop.
- A dismissed one-time alarm must not trigger again.
- A recurring alarm must calculate its next scheduled occurrence.
- The alarm must transition to an appropriate lifecycle state.

### FR-09: Snooze Alarm

Users must be able to snooze a currently ringing alarm.

Expected behaviour:

- Snooze duration must be configurable.
- The alarm must trigger again after the snooze duration.
- Snoozing must preserve the original alarm identity.
- Snoozed alarms must be considered by the scheduler.
- Snoozing must not accidentally create duplicate alarms.

### FR-10: Recurring Alarms

The application should support recurring alarms.

Initial recurrence options:

- One-time alarm.
- Daily alarm.
- Weekday-based alarm.
- Custom days of the week.

Expected behaviour:

- Recurring alarms must calculate their next occurrence correctly.
- Dismissing a recurring alarm must schedule its next occurrence.
- Recurrence calculations must account for calendar dates and timezone behaviour.
- Recurring alarms must remain configured after triggering.

### FR-11: Application Startup and Missed Alarms

When the application starts:

- Load previously persisted alarms.
- Restore their enabled/disabled configuration.
- Reconstruct the scheduler's pending alarm list.
- Identify alarms that were missed while the application was not running.

For missed alarms, the initial behaviour should be to notify the user that an alarm was missed rather than automatically playing an overdue alarm.

The application must not silently discard missed alarm information.

### FR-12: CLI Commands

The application must provide the following commands:

| Command | Description |
|---|---|
| add | Create an alarm |
| list | Display configured alarms |
| update | Modify an existing alarm |
| delete | Delete an alarm |
| enable | Enable an alarm |
| disable | Disable an alarm |
| run | Start the alarm monitoring process |

The CLI must:

- Provide clear usage instructions.
- Validate arguments.
- Display meaningful success and error messages.
- Return appropriate exit codes.
- Support a help command.

---

## 4. Non-Functional Requirements

### NFR-01: Simplicity

- Use Python as the primary implementation language.
- Prefer Python standard library functionality.
- Avoid unnecessary frameworks and dependencies.
- Avoid introducing a database server or external infrastructure.

### NFR-02: Reliability

- Alarm configurations must survive application restarts.
- File writes should be atomic where practical.
- Storage failures must be handled explicitly.
- The scheduler must avoid duplicate alarm triggering.
- Errors in one notification must not terminate unrelated alarm scheduling.

### NFR-03: Maintainability

The application must have clearly separated responsibilities:

- Domain models.
- Business logic.
- Persistence.
- Scheduling.
- Notifications.
- CLI interaction.

Components should communicate through clear interfaces.

### NFR-04: Testability

- Business logic must be independently testable.
- Time-dependent functionality must support an injectable clock.
- Tests must not depend on waiting for actual time to pass.
- External side effects such as notifications and filesystem operations should be replaceable or mockable.

### NFR-05: Performance

- The application should comfortably support multiple alarms.
- Scheduling must avoid unnecessary busy polling.
- Alarm configuration operations should be lightweight.
- No unnecessary background processing should be introduced.

### NFR-06: Portability

- Prefer cross-platform Python standard library functionality.
- Terminal notification behaviour should degrade gracefully across operating systems.
- Document any operating-system-specific audio limitations.

---

## 5. Domain Model

### Alarm

The primary domain entity should contain:

| Attribute | Description |
|---|---|
| id | Unique alarm identifier |
| time | Scheduled time or next occurrence |
| label | Optional user-defined description |
| enabled | Whether the alarm is active |
| recurrence | Recurrence configuration |
| snooze_duration | Configured snooze duration |
| created_at | Alarm creation timestamp |

Additional runtime state may be maintained separately from the persistent alarm configuration.

### Alarm Lifecycle

The application should model the following states:

- SCHEDULED: Waiting for its next occurrence.
- RINGING: Currently notifying the user.
- SNOOZED: Temporarily postponed.
- DISABLED: Not eligible for scheduling.
- DISMISSED: Current occurrence has been dismissed.

The implementation should distinguish between an alarm's persistent configuration and the runtime state of an individual occurrence.

---

## 6. Persistence Requirements

Use a local JSON file for storing alarm configurations.

Expected behaviour:

- Load alarm configurations during application startup.
- Persist changes after create, update, delete, enable, and disable operations.
- Handle missing storage files.
- Handle malformed JSON.
- Avoid silently overwriting corrupted storage.
- Use safe file-writing practices, preferably atomic replacement.
- Validate loaded data before reconstructing domain objects.

The scheduler's internal state should be reconstructed from persisted alarm configurations rather than requiring a separately persisted scheduling queue.

Suggested storage location:

`data/alarms.json`

No database is required.

---

## 7. Architecture Requirements

The application should follow a simple modular architecture.

Proposed responsibilities:

| Component | Responsibility |
|---|---|
| Models | Domain entities and validation |
| Alarm Service | Business operations on alarms |
| Storage | JSON persistence |
| Scheduler | Determine and trigger due alarms |
| Notifier | Terminal and audio notifications |
| CLI | User interaction and command parsing |
| Main | Application initialization and orchestration |

The architecture must avoid coupling business logic directly to CLI input/output or notification mechanisms.

No microservices, distributed architecture, web APIs, or unnecessary abstraction layers should be introduced.

---

## 8. Error Handling and Edge Cases

The application must handle the following scenarios:

1. Invalid alarm time.
2. Attempt to delete an unknown alarm ID.
3. Attempt to update an unknown alarm ID.
4. Missing JSON storage file.
5. Corrupted JSON storage file.
6. Filesystem read/write failure.
7. Two alarms scheduled for the same time.
8. Adding an earlier alarm while the scheduler is waiting.
9. Deleting an alarm while the scheduler is waiting.
10. Disabling an alarm while the scheduler is waiting.
11. Application restart after an alarm has been missed.
12. Snoozing an alarm multiple times.
13. System clock moving forward or backward.
14. Scheduler shutdown while waiting.
15. Notification failure.
16. Recurring alarm around a daylight-saving transition where applicable.
17. Application restart while an alarm was previously ringing or snoozed.

Each scenario should have a defined expected behaviour and corresponding tests.

---

## 9. Testing Requirements

### Unit Tests

Cover:

- Alarm creation and validation.
- Alarm updates.
- Alarm deletion.
- Enable/disable operations.
- Recurrence calculations.
- Snooze calculations.
- JSON serialization and deserialization.
- Scheduler due-time calculations.

### Scheduler Tests

Cover:

- Triggering an alarm at the scheduled time.
- Multiple alarms triggering simultaneously.
- Scheduler interruption.
- Alarm configuration changes.
- Clock adjustments.
- Snoozed alarms.
- Graceful shutdown.
- Preventing duplicate triggers.

### Integration Tests

Cover complete workflows:

- Create an alarm and verify persistence.
- Restart and reload alarms.
- Start the scheduler and trigger an alarm.
- Snooze and dismiss alarms.
- Modify or delete alarms while the scheduler is running.

Testing should use temporary storage and injected clocks wherever appropriate.

The test suite should be runnable without external services.

---

## 10. Constraints and Technical Choices

| Area | Decision |
|---|---|
| Language | Python |
| Interface | Command-line interface |
| Persistence | Local JSON file |
| Database | Not required |
| External services | Not required |
| Dependencies | Python standard library preferred |
| Scheduler | Local in-process scheduler |
| Time source | Operating system clock |
| Testing | unittest or pytest |
| Configuration | Local application configuration |

Third-party dependencies should only be introduced when there is a clear technical justification.

---

## 11. Out of Scope

The following are explicitly excluded:

- Web application.
- Desktop GUI.
- Mobile application.
- Remote database.
- Cloud synchronization.
- User authentication.
- Multi-user support.
- Distributed scheduling.
- Operating-system service or daemon installation.
- Waking a powered-off or sleeping computer.
- Remote notifications.

The application must remain running in the foreground for scheduled alarms to trigger.

---

## 12. Acceptance Criteria

The application will be considered complete when:

- [x] Users can create alarms through CLI commands.
- [x] Users can list configured alarms.
- [x] Users can update and delete alarms.
- [x] Users can enable and disable alarms.
- [x] Alarm configurations persist across application restarts.
- [x] The scheduler detects upcoming alarms.
- [x] Due alarms trigger notifications.
- [x] Multiple simultaneous alarms are supported.
- [x] Users can dismiss ringing alarms.
- [x] Users can snooze alarms.
- [x] Recurring alarms calculate subsequent occurrences correctly.
- [x] Missed alarms are handled according to the defined startup behaviour.
- [x] Invalid inputs and storage errors are handled gracefully.
- [x] Scheduler shutdown is handled cleanly.
- [x] Automated unit and integration tests pass.
- [x] README documents installation, usage, architecture and limitations.

---

## 13. Implementation Milestones

Implementation should be incremental.

| Milestone | Scope | Deliverable |
|---|---|---|
| M1 | Domain model | Alarm entity and validation |
| M2 | Persistence | JSON storage |
| M3 | Alarm service | Create, delete, update, list |
| M4 | Scheduler | Detect and trigger due alarms |
| M5 | Notifications | Terminal/audio notifications |
| M6 | CLI | User-facing commands |
| M7 | Snooze and recurrence | Extended alarm lifecycle |
| M8 | Integration | Complete application |
| M9 | Hardening | Edge cases, tests and documentation |

Each milestone must be implemented, tested and reviewed before proceeding to the next.

---

## 14. Definition of Done

A feature is considered complete only when:

1. Its implementation matches the agreed requirements.
2. Relevant automated tests have been written.
3. Tests have been executed successfully.
4. Edge cases have been considered.
5. No unrelated functionality has been modified.
6. Code follows the approved architecture.
7. Any deviations are documented and approved.

The final submission must include the source code, automated tests, README, and relevant design documentation.
