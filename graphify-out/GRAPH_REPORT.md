# Graph Report - DriverManager  (2026-11-09)

## Corpus Check
- 35 files · ~37,438 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 3 file(s) not represented in the graph (top: (none) 1, .bat 1, .ico 1)

## Summary
- 740 nodes · 1865 edges · 30 communities (19 shown, 11 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 59 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `3446ee20`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- tr
- DriverManagerGUI
- test_core.py
- driver_scanner.py
- updater.py
- gui.py
- gpu_check.py
- auto_scan.py
- ._intro
- deep_catalog.py
- inf_rank.py
- SmoothScrollFrame
- driver_history.py
- test_history.py
- test_updater.py
- widgets.py
- test_i18n.py
- single_instance.py
- ScanBar
- Tween
- ModernEventInterceptor
- config.py
- prefs.py
- Switch

## God Nodes (most connected - your core abstractions)
1. `tr()` - 115 edges
2. `DriverManagerGUI` - 75 edges
3. `main()` - 21 edges
4. `backup_current_drivers()` - 21 edges
5. `FastWMI` - 20 edges
6. `SmoothScrollFrame` - 18 edges
7. `deep_scan_peripherals()` - 18 edges
8. `Tween` - 17 edges
9. `install_catalog_cab_updates()` - 17 edges
10. `verify_candidate()` - 16 edges

## Surprising Connections (you probably didn't know these)
- `write_manifest()` --calls--> `release_asset_url()`  [INFERRED]
  build.py → src/config.py
- `DriverManagerGUI` --uses--> `ScanBar`  [INFERRED]
  src/gui.py → src/widgets.py
- `DriverManagerGUI` --uses--> `SmoothScrollFrame`  [INFERRED]
  src/gui.py → src/widgets.py
- `DriverManagerGUI` --uses--> `Switch`  [INFERRED]
  src/gui.py → src/widgets.py
- `DriverManagerGUI` --uses--> `Tween`  [INFERRED]
  src/gui.py → src/widgets.py

## Import Cycles
- None detected.

## Communities (30 total, 11 thin omitted)

### Community 0 - "tr"
Cohesion: 0.05
Nodes (49): install_catalog_cab_updates(), dism_component_cleanup(), find_obsolete_driver_packages(), list_driver_packages(), remove_obsolete_driver_packages(), backups_needed_for_undo(), file_hash(), find_in_backups() (+41 more)

### Community 1 - "DriverManagerGUI"
Cohesion: 0.05
Nodes (15): DriverManagerGUI, work(), task(), task(), task(), on_enter(), on_leave(), toggle() (+7 more)

### Community 2 - "test_core.py"
Cohesion: 0.09
Nodes (21): _client(), handler(), _FakeWmi, _info(), _Obj, _pkg(), _row(), _table_client() (+13 more)

### Community 4 - "updater.py"
Cohesion: 0.14
Nodes (13): subject_organization(), task(), apply_and_restart(), check(), _check_signer(), configured(), download(), due() (+5 more)

### Community 5 - "gui.py"
Cohesion: 0.11
Nodes (5): fmt_bytes(), _process_start(), _selftest_done(), verify_line(), dark_title_bar()

### Community 6 - "gpu_check.py"
Cohesion: 0.07
Nodes (32): published_driver_names(), select_obsolete(), _version_key(), amd_covered(), amd_installed_version(), check_gpu(), check_gpus(), intel_covered() (+24 more)

### Community 7 - "auto_scan.py"
Cohesion: 0.11
Nodes (18): _command_line(), get_frequency(), last_result(), main(), mark_seen(), next_run(), notification_text(), _powershell() (+10 more)

### Community 9 - "deep_catalog.py"
Cohesion: 0.06
Nodes (35): cab_links_for(), catalog_queries(), CatalogResult, check_device(), cleanup_package_cache(), collect_problem_devices(), deep_scan_peripherals(), device_ids_map() (+27 more)

### Community 10 - "inf_rank.py"
Cohesion: 0.08
Nodes (23): read(), configured_language(), fmt_date(), fmt_day_month(), resolve(), save_language(), windows_language(), best_match() (+15 more)

### Community 12 - "driver_history.py"
Cohesion: 0.14
Nodes (14): add_ignored_update(), build_entry(), add_ignored(), ignore_key(), is_ignored(), keys_for(), load_entries(), remove_entry() (+6 more)

### Community 13 - "test_history.py"
Cohesion: 0.31
Nodes (8): _catalog_entry(), _inf(), test_backups_needed_for_undo(), test_build_entry_tracks_added_removed_and_previous(), test_nvidia_restores_packages_removed_by_installer(), test_undo_plan_refusals(), test_undo_plan_removes_new_package_and_keeps_previous(), test_undo_plan_restores_previous_from_backup_by_hash()

### Community 14 - "test_updater.py"
Cohesion: 0.06
Nodes (18): default_name(), export(), _plain(), system_info(), inf(), test_feature_score_from_ddinstall_section(), test_identifier_scores_follow_microsoft_ranges(), test_models_decoration_choice() (+10 more)

### Community 15 - "widgets.py"
Cohesion: 0.18
Nodes (6): ease_in_out_cubic(), ease_out_back(), ease_out_quint(), mix(), _system_animations_enabled(), windows_uses_dark()

### Community 19 - "test_i18n.py"
Cohesion: 0.22
Nodes (5): fields(), test_every_text_has_an_english_translation(), test_no_unused_translations(), test_placeholders_match(), tr_keys()

### Community 20 - "single_instance.py"
Cohesion: 0.21
Nodes (7): another_running(), bring_to_front(), claim(), _k32(), request_focus(), watch(), check()

### Community 21 - "ScanBar"
Cohesion: 0.21
Nodes (3): run(), ScanBar, SmoothTimer

### Community 23 - "Tween"
Cohesion: 0.29
Nodes (3): ease_in_cubic(), step(), Tween

### Community 26 - "config.py"
Cohesion: 0.07
Nodes (23): _arg(), main(), make_icon(), pyinstaller(), version_file(), write_manifest(), release_asset_url(), release_manifest_url() (+15 more)

### Community 28 - "prefs.py"
Cohesion: 0.60
Nodes (3): get(), load(), set_value()

## Knowledge Gaps
- **11 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `tr()` connect `tr` to `DriverManagerGUI`, `driver_scanner.py`, `updater.py`, `gui.py`, `gpu_check.py`, `auto_scan.py`, `deep_catalog.py`, `inf_rank.py`, `ModernEventInterceptor`, `config.py`?**
  _High betweenness centrality (0.260) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `DriverManagerGUI` (e.g. with `ScanBar` and `SmoothScrollFrame`) actually correct?**
  _`DriverManagerGUI` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Should `tr` be split into smaller, more focused modules?**
  _Cohesion score 0.05414488424197162 - nodes in this community are weakly interconnected._
- **Why does `DriverManagerGUI` connect `DriverManagerGUI` to `tr`, `driver_scanner.py`, `gui.py`, `._intro`, `deep_catalog.py`, `SmoothScrollFrame`, `ScanBar`, `Tween`, `Switch`?**
  _High betweenness centrality (0.078) - this node is a cross-community bridge._
- **Should `DriverManagerGUI` be split into smaller, more focused modules?**
  _Cohesion score 0.0547008547008547 - nodes in this community are weakly interconnected._
- **Why does `SmoothScrollFrame` connect `SmoothScrollFrame` to `DriverManagerGUI`, `gui.py`, `widgets.py`?**
  _High betweenness centrality (0.043) - this node is a cross-community bridge._
- **Should `test_core.py` be split into smaller, more focused modules?**
  _Cohesion score 0.08636977058029689 - nodes in this community are weakly interconnected._