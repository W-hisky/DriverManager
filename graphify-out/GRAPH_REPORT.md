# Graph Report - DriverManager  (2026-11-09)

## Corpus Check
- 33 files · ~36,802 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 4 file(s) not represented in the graph (top: (none) 1, .bat 1, .ico 1)

## Summary
- 724 nodes · 1803 edges · 30 communities (21 shown, 9 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 55 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- main.py
- DriverManagerGUI
- test_core.py
- driver_scanner.py
- updater.py
- driver_installer.py
- gpu_check.py
- auto_scan.py
- Tween
- deep_catalog.py
- inf_rank.py
- gui.py
- driver_history.py
- test_history.py
- test_inf_rank.py
- driver_cleanup.py
- test_i18n.py
- single_instance.py
- ModernEventInterceptor
- Switch
- SmoothScrollFrame
- config.py
- ScanBar
- ._task_full_scan
- test_wu.py

## God Nodes (most connected - your core abstractions)
1. `tr()` - 114 edges
2. `DriverManagerGUI` - 71 edges
3. `main()` - 21 edges
4. `FastWMI` - 20 edges
5. `backup_current_drivers()` - 20 edges
6. `deep_scan_peripherals()` - 18 edges
7. `install_catalog_cab_updates()` - 17 edges
8. `SmoothScrollFrame` - 16 edges
9. `verify_candidate()` - 16 edges
10. `Tween` - 15 edges

## Surprising Connections (you probably didn't know these)
- `write_manifest()` --calls--> `release_asset_url()`  [INFERRED]
  build.py → src/config.py
- `task()` --calls--> `export()`  [EXTRACTED]
  src/gui.py → src/diagnostics.py
- `task()` --calls--> `FastWMI`  [EXTRACTED]
  src/gui.py → src/wmi_fast.py
- `work()` --calls--> `set_value()`  [EXTRACTED]
  src/gui.py → src/prefs.py
- `work()` --calls--> `check()`  [EXTRACTED]
  src/gui.py → src/updater.py

## Import Cycles
- None detected.

## Communities (30 total, 9 thin omitted)

### Community 0 - "main.py"
Cohesion: 0.15
Nodes (12): install_windows_update_drivers(), update_game_runtimes(), check_all_gpus(), check_nvidia_update(), check_windows_update_drivers(), list_third_party_drivers(), nvidia_info(), _print_gpu() (+4 more)

### Community 1 - "DriverManagerGUI"
Cohesion: 0.06
Nodes (21): dark_title_bar(), DriverManagerGUI, work(), task(), task(), task(), on_enter(), on_leave() (+13 more)

### Community 2 - "test_core.py"
Cohesion: 0.09
Nodes (21): _client(), handler(), _FakeWmi, _info(), _Obj, _pkg(), _row(), _table_client() (+13 more)

### Community 4 - "updater.py"
Cohesion: 0.09
Nodes (16): task(), apply_and_restart(), check(), _check_signer(), configured(), download(), due(), is_newer() (+8 more)

### Community 5 - "driver_installer.py"
Cohesion: 0.12
Nodes (12): backup_current_drivers(), backups_to_prune(), download_file(), driverstore_fingerprint(), enable_gpu_msi_mode(), install_nvidia_driver(), list_backups(), prune_old_backups() (+4 more)

### Community 6 - "gpu_check.py"
Cohesion: 0.07
Nodes (29): amd_covered(), amd_installed_version(), check_gpu(), check_gpus(), intel_covered(), is_newer(), normalize_name(), nv_date_to_iso() (+21 more)

### Community 7 - "auto_scan.py"
Cohesion: 0.11
Nodes (18): _command_line(), get_frequency(), last_result(), main(), mark_seen(), next_run(), notification_text(), _powershell() (+10 more)

### Community 8 - "Tween"
Cohesion: 0.23
Nodes (4): run(), done(), SmoothTimer, Tween

### Community 9 - "deep_catalog.py"
Cohesion: 0.05
Nodes (39): add_ignored_update(), cab_links_for(), catalog_queries(), CatalogResult, check_device(), cleanup_package_cache(), collect_problem_devices(), deep_scan_peripherals() (+31 more)

### Community 10 - "inf_rank.py"
Cohesion: 0.11
Nodes (16): best_match(), best_match_in_package(), _better(), current_os(), _decoration_applies(), feature_score(), _fmt(), Inf (+8 more)

### Community 11 - "gui.py"
Cohesion: 0.10
Nodes (6): ease_in_cubic(), fmt_bytes(), _process_start(), _selftest_done(), _system_animations_enabled(), windows_uses_dark()

### Community 12 - "driver_history.py"
Cohesion: 0.07
Nodes (32): backups_needed_for_undo(), build_entry(), file_hash(), find_in_backups(), load_history(), _pnputil(), protected_infs(), record_install() (+24 more)

### Community 13 - "test_history.py"
Cohesion: 0.31
Nodes (8): _catalog_entry(), _inf(), test_backups_needed_for_undo(), test_build_entry_tracks_added_removed_and_previous(), test_nvidia_restores_packages_removed_by_installer(), test_undo_plan_refusals(), test_undo_plan_removes_new_package_and_keeps_previous(), test_undo_plan_restores_previous_from_backup_by_hash()

### Community 14 - "test_inf_rank.py"
Cohesion: 0.24
Nodes (5): inf(), test_feature_score_from_ddinstall_section(), test_identifier_scores_follow_microsoft_ranges(), test_models_decoration_choice(), test_verify_and_refine_tries_alternative_then_gives_up()

### Community 15 - "driver_cleanup.py"
Cohesion: 0.14
Nodes (6): dism_component_cleanup(), find_obsolete_driver_packages(), list_driver_packages(), remove_obsolete_driver_packages(), select_obsolete(), _version_key()

### Community 19 - "test_i18n.py"
Cohesion: 0.22
Nodes (5): fields(), test_every_text_has_an_english_translation(), test_no_unused_translations(), test_placeholders_match(), tr_keys()

### Community 20 - "single_instance.py"
Cohesion: 0.19
Nodes (7): another_running(), bring_to_front(), claim(), _k32(), request_focus(), watch(), check()

### Community 23 - "Switch"
Cohesion: 0.24
Nodes (3): ease_out_back(), Switch, step()

### Community 26 - "config.py"
Cohesion: 0.05
Nodes (27): _arg(), main(), make_icon(), pyinstaller(), version_file(), write_manifest(), release_asset_url(), release_manifest_url() (+19 more)

### Community 27 - "ScanBar"
Cohesion: 0.22
Nodes (4): step(), ease_in_out_cubic(), mix(), ScanBar

### Community 29 - "test_wu.py"
Cohesion: 0.36
Nodes (5): test_search_failure_is_reported(), test_search_skips_ignored(), test_to_item_has_catalog_shape(), test_windows_update_wins_over_catalog(), _update()

## Knowledge Gaps
- **9 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `tr()` connect `DriverManagerGUI` to `main.py`, `updater.py`, `driver_installer.py`, `gpu_check.py`, `auto_scan.py`, `deep_catalog.py`, `inf_rank.py`, `gui.py`, `driver_history.py`, `driver_cleanup.py`, `ModernEventInterceptor`, `config.py`, `._task_full_scan`?**
  _High betweenness centrality (0.266) - this node is a cross-community bridge._
- **Should `DriverManagerGUI` be split into smaller, more focused modules?**
  _Cohesion score 0.05875077303648732 - nodes in this community are weakly interconnected._
- **Why does `DriverManagerGUI` connect `DriverManagerGUI` to `driver_installer.py`, `Tween`, `gui.py`, `driver_cleanup.py`, `Switch`, `._task_full_scan`?**
  _High betweenness centrality (0.074) - this node is a cross-community bridge._
- **Should `test_core.py` be split into smaller, more focused modules?**
  _Cohesion score 0.08961593172119488 - nodes in this community are weakly interconnected._
- **Why does `SmoothScrollFrame` connect `SmoothScrollFrame` to `DriverManagerGUI`, `gui.py`?**
  _High betweenness centrality (0.043) - this node is a cross-community bridge._
- **Should `updater.py` be split into smaller, more focused modules?**
  _Cohesion score 0.08571428571428572 - nodes in this community are weakly interconnected._
- **Should `driver_installer.py` be split into smaller, more focused modules?**
  _Cohesion score 0.12169312169312169 - nodes in this community are weakly interconnected._