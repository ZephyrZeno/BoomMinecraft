# Main entry report decoding, ABI14

The native report decoder derives report576 / ABI14 only when the manifest's
`server_help=true` agrees with a bound `game_entry` model, original System
phases1/2/3 are requested, and the explicit arguments are exactly `['--help']`.
An asserted manifest report size cannot override those conditions. The decoder
accepts the frozen game model's `argv.rows` representation and an explicit
`arguments` list; if both exist, their strings and lengths must agree.

The first544 bytes retain the prior protocol. New DWORD observations are:

| Offset | Observation |
| --- | --- |
| 544 | original Main class initialized |
| 548 | original Main called |
| 552 | original Main returned |
| 556 | argc |
| 560,564,568,572 | Game Context kind, PC, method, depth |

Phase2 success uses its own return flag, result0, and observed VM level2.
Phase3 success uses its own called/returned flags, Context0/depth0, and VM2→4.
The latest-main capture at296 may describe a later argv/Logger/Main failure;
it must not retroactively invalidate the earlier successful phase snapshots.
When the Game helper ran, its Context at560 must equal that latest-main capture.
If Phase3 failed first, the entire Game region544..575 must remain zero.

The three new event flags are strict booleans with call/return/initializer
ordering. A normal Main return requires Context.kind0 and depth0. With completed
Phase3, the reported argc must match the bound argument list even if array
allocation or Main `<clinit>` failed before main_called. Such a failed attempt
requires a real nonzero Context; a false all-zero failure is rejected. Source
stops retain the exact first-process and latest-main diagnostic rows, with
latest-main attribution and normal source-admission filtering. Exit70 can record
an actual pre-entry/Java exception; exit86 requires a genuine source-stop record.
Native owner status68, cleanup/worker checks, and Parker/IO ownership rules remain
active. EntryComplete72 must match the final requested Game outcome rather than
only Phase3 completion.

The result adds `game_entry`, `original_game_Main_called`,
`original_game_Main_returned`, and `server_help_completed`. Phase3's own
`completed` value remains independent of subsequent Main failure. Even a normal
help return leaves `game_started`, `world_created`, and `full_VM_bootstrap` false.
The report says what the original entry did; it does not establish complete
Minecraft startup or a working world.

The ABI14 decoder source is frozen at SHA-256
`5fa4043c1367e7961979f7022a9abb2cea3457860cdc085360785d759491b613`.
Run-VmEntry's interface is unchanged. Forty-five focused protocol tests pass:
the previous25 cases, including real historical448 compatibility and real544
read-only Phase3 decoding, plus20 ABI14 cases. The576 cases are explicit
protocol fixtures, not native Main execution. No old report or accepted
observation is overwritten, and this update does not retrofit a new decoder pin
into historical execution proofs. A new original-Main source selection and
native execution are owned by the main agent.
