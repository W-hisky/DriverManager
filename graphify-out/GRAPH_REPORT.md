# Graph Report - DriverManager  (2026-11-09)

## Corpus Check
- 31 files · ~34,598 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 4 file(s) not represented in the graph (top: (none) 1, .bat 1, .ico 1)

## Summary
- 683 nodes · 1709 edges · 28 communities (20 shown, 8 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 54 edges (avg confidence: 0.85)
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
- ignore_list.py
- SmoothScrollFrame
- mix
- ScanBar

## God Nodes (most connected - your core abstractions)
1. `tr()` - 110 edges
2. `DriverManagerGUI` - 69 edges
3. `main()` - 21 edges
4. `FastWMI` - 20 edges
5. `backup_current_drivers()` - 20 edges
6. `deep_scan_peripherals()` - 18 edges
7. `install_catalog_cab_updates()` - 17 edges
8. `verify_candidate()` - 16 edges
9. `Tween` - 15 edges
10. `snapshot_infs()` - 15 edges

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

## Communities (28 total, 8 thin omitted)

### Community 0 - "main.py"
Cohesion: 0.13
Nodes (13): remove_obsolete_driver_packages(), install_windows_update_drivers(), update_game_runtimes(), check_all_gpus(), check_nvidia_update(), check_windows_update_drivers(), list_third_party_drivers(), nvidia_info() (+5 more)

### Community 1 - "DriverManagerGUI"
Cohesion: 0.06
Nodes (22): clean_gpu_shader_cache(), create_system_restore_point(), dark_title_bar(), DriverManagerGUI, work(), task(), task(), on_enter() (+14 more)

### Community 2 - "test_core.py"
Cohesion: 0.09
Nodes (21): _client(), handler(), _FakeWmi, _info(), _Obj, _pkg(), _row(), _table_client() (+13 more)

### Community 3 - "driver_scanner.py"
Cohesion: 0.10
Nodes (7): enable_gpu_msi_mode(), FastWMI, test_search_failure_is_reported(), test_search_skips_ignored(), test_to_item_has_catalog_shape(), test_windows_update_wins_over_catalog(), _update()

### Community 4 - "updater.py"
Cohesion: 0.09
Nodes (15): task(), apply_and_restart(), check(), _check_signer(), configured(), download(), due(), is_newer() (+7 more)

### Community 5 - "driver_installer.py"
Cohesion: 0.15
Nodes (11): backup_current_drivers(), backups_to_prune(), download_file(), driverstore_fingerprint(), install_nvidia_driver(), list_backups(), prune_old_backups(), _read_manifest() (+3 more)

### Community 6 - "gpu_check.py"
Cohesion: 0.07
Nodes (29): amd_covered(), amd_installed_version(), check_gpu(), check_gpus(), intel_covered(), is_newer(), normalize_name(), nv_date_to_iso() (+21 more)

### Community 7 - "auto_scan.py"
Cohesion: 0.10
Nodes (18): _command_line(), get_frequency(), last_result(), main(), mark_seen(), next_run(), notification_text(), _powershell() (+10 more)

### Community 8 - "Tween"
Cohesion: 0.18
Nodes (5): run(), done(), SmoothTimer, step(), Tween

### Community 9 - "deep_catalog.py"
Cohesion: 0.05
Nodes (38): add_ignored_update(), cab_links_for(), catalog_queries(), CatalogResult, check_device(), cleanup_package_cache(), collect_problem_devices(), deep_scan_peripherals() (+30 more)

### Community 10 - "inf_rank.py"
Cohesion: 0.05
Nodes (28): _arg(), main(), make_icon(), pyinstaller(), version_file(), write_manifest(), release_asset_url(), release_manifest_url() (+20 more)

### Community 11 - "gui.py"
Cohesion: 0.10
Nodes (6): ease_in_cubic(), ease_out_back(), _process_start(), _selftest_done(), _system_animations_enabled(), windows_uses_dark()

### Community 12 - "driver_history.py"
Cohesion: 0.16
Nodes (14): backups_needed_for_undo(), build_entry(), file_hash(), find_in_backups(), load_history(), _pnputil(), protected_infs(), record_install() (+6 more)

### Community 13 - "test_history.py"
Cohesion: 0.31
Nodes (8): _catalog_entry(), _inf(), test_backups_needed_for_undo(), test_build_entry_tracks_added_removed_and_previous(), test_nvidia_restores_packages_removed_by_installer(), test_undo_plan_refusals(), test_undo_plan_removes_new_package_and_keeps_previous(), test_undo_plan_restores_previous_from_backup_by_hash()

### Community 14 - "test_inf_rank.py"
Cohesion: 0.24
Nodes (5): inf(), test_feature_score_from_ddinstall_section(), test_identifier_scores_follow_microsoft_ranges(), test_models_decoration_choice(), test_verify_and_refine_tries_alternative_then_gives_up()

### Community 15 - "driver_cleanup.py"
Cohesion: 0.15
Nodes (5): dism_component_cleanup(), find_obsolete_driver_packages(), list_driver_packages(), select_obsolete(), _version_key()

### Community 19 - "test_i18n.py"
Cohesion: 0.22
Nodes (5): fields(), test_every_text_has_an_english_translation(), test_no_unused_translations(), test_placeholders_match(), tr_keys()

### Community 20 - "single_instance.py"
Cohesion: 0.19
Nodes (7): another_running(), bring_to_front(), claim(), _k32(), request_focus(), watch(), check()

### Community 23 - "ignore_list.py"
Cohesion: 0.11
Nodes (19): configured_language(), resolve(), save_language(), windows_language(), add_ignored(), ignore_key(), is_ignored(), keys_for() (+11 more)

### Community 26 - "mix"
Cohesion: 0.29
Nodes (3): step(), mix(), Switch

## Knowledge Gaps
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `tr()` connect `DriverManagerGUI` to `main.py`, `driver_scanner.py`, `updater.py`, `driver_installer.py`, `gpu_check.py`, `auto_scan.py`, `deep_catalog.py`, `inf_rank.py`, `gui.py`, `driver_history.py`, `driver_cleanup.py`, `ModernEventInterceptor`, `ignore_list.py`?**
  _High betweenness centrality (0.266) - this node is a cross-community bridge._
- **Should `main.py` be split into smaller, more focused modules?**
  _Cohesion score 0.13333333333333333 - nodes in this community are weakly interconnected._
- **Why does `DriverManagerGUI` connect `DriverManagerGUI` to `Tween`, `driver_scanner.py`, `gui.py`, `driver_cleanup.py`?**
  _High betweenness centrality (0.078) - this node is a cross-community bridge._
- **Should `DriverManagerGUI` be split into smaller, more focused modules?**
  _Cohesion score 0.055825242718446605 - nodes in this community are weakly interconnected._
- **Why does `FastWMI` connect `driver_scanner.py` to `main.py`, `DriverManagerGUI`, `auto_scan.py`, `gui.py`, `driver_cleanup.py`?**
  _High betweenness centrality (0.037) - this node is a cross-community bridge._
- **Should `test_core.py` be split into smaller, more focused modules?**
  _Cohesion score 0.08961593172119488 - nodes in this community are weakly interconnected._
- **Should `driver_scanner.py` be split into smaller, more focused modules?**
  _Cohesion score 0.0960591133004926 - nodes in this community are weakly interconnected._