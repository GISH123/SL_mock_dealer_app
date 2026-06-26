# Mock Dealer App BAC

## 20260528 update : final Mock Dealer BAC/DT tester for pydealerLight BAC

This update finalizes the Mock Dealer App used to test the latest `pydealerLight BAC` flow.

### Main changes

- Added a startup launcher for selecting:
  - control mode: `TCP`, `HTTP`, or `Both`
  - game mode: `DT (3 slots)` or `BAC Classic (6 slots)`
  - optional DVR recording toggle
- Finalized BAC Classic 6-slot testing flow:
  - index `1` = Player card 1
  - index `2` = Player card 2
  - index `3` = Banker card 1
  - index `4` = Banker card 2
  - index `5` = Player card 3
  - index `6` = Banker card 3
- Added BAC auto-dispatch logic based on Baccarat drawing rules:
  - dispatch `[1, 3]` together first
  - dispatch `[2, 4]` together after both first cards are detected
  - dispatch `5` only when the Player needs a third card
  - dispatch `6` only when the Banker needs a third card
  - finish the round automatically when the Baccarat rule is complete
- Improved BAC pending-index handling:
  - cardback / empty results are ignored for active BAC indexes
  - pending indexes are re-dispatched until a real card result is received
  - delayed stale cardback / empty results will not overwrite an already detected real card
- Preserved DT 3-slot mode for smaller-flow testing.
- Preserved manual dispatch and `Dispatch All` / burst-style testing.
- Ensured `Save Result` is sent before `Stop Prediction` in scheduled auto flows.
- Added configurable timing controls in the UI:
  - dispatch interval
  - save gap
  - stop gap
  - round gap
  - stuck-round skip timeout
- Added editable dispatch order, defaulting to:

```text
1, 3, 2, 4, 5, 6
```

- Persisted timing/order settings in `last_save_default_gap_value.env` so the next run can reuse the last test setup.
- Added scrollable UI event logs and detailed TCP / HTTP / DVR command logs for debugging.
- Added TCP protocol support for the detector-side command flow:
  - login reply
  - start prediction
  - dispatch index
  - save result
  - stop prediction
  - cancel result
  - prediction result update
- Added HTTP control support for pydealerLight HTTP API testing:
  - `/start_predict`
  - `/dispatch_index`
  - `/save_result`
  - `/stop_predict`
- Added optional DVR start/stop record integration using the 30-byte DVR packet format.
- Updated PyInstaller build spec for `MockDealerBAC` versioned builds.

### Current role of this project

This project is the BAC/DT mock dealer tool for testing `pydealerLight BAC` without requiring the real dealer client.

Recommended current usage:

```text
MockDealerBAC  ->  pydealerLight BAC  ->  model engine
```

Use this mock dealer to verify:

- BAC index dispatch order
- BAC 4-card / 5-card / 6-card round behavior
- Save Result before Stop Prediction
- TCP / HTTP / Both control modes
- CSV and image output behavior in pydealerLight
- long-running auto-dispatch stability

### Important runtime notes

- `.env` controls pydealerLight host/port, HTTP base URL, table/device/stream IDs, and DVR connection settings.
- `last_save_default_gap_value.env` stores UI timing and order settings.
- The full mock dealer repository is expected to provide shared runtime helpers such as `shared_runtime.py`, build helpers such as `shared_build_utils.py`, and card image resources such as `card_shown_ui`.
- The generated executable logs to the runtime `logs/` folder.

## Documents

User-facing documents are organized under:

```text
/doc
```

Current documents:

```text
/doc/README.md
/doc/MockDealerBAC_User_Manual.html
```

Start with `doc/README.md`, then open `MockDealerBAC_User_Manual.html` in a browser for the full end-user guide.
