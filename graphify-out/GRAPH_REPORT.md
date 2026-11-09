# Graph Report - DriverManager  (2026-11-09)

## Corpus Check
- 31 files · ~34,395 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 4 file(s) not represented in the graph (top: (none) 1, .bat 1, .ico 1)

## Summary
- 681 nodes · 1707 edges · 28 communities (20 shown, 8 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 54 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- build.py
- DriverManagerGUI
- test_core.py
- driver_scanner.py
- updater.py
- deep_catalog.py
- gpu_check.py
- auto_scan.py
- query_ms_catalog
- wu_drivers.py
- inf_rank.py
- Tween
- driver_installer.py
- test_history.py
- test_inf_rank.py
- i18n.py
- diagnostics.py
- ModernEventInterceptor
- ignore_list.py
- deep_scan_peripherals
- test_updater.py
- prefs.py

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

### Community 0 - "build.py"
Cohesion: 0.17
Nodes (8): _arg(), main(), make_icon(), pyinstaller(), version_file(), write_manifest(), release_asset_url(), release_manifest_url()

### Community 1 - "DriverManagerGUI"
Cohesion: 0.06
Nodes (21): composited(), dark_title_bar(), DriverManagerGUI, work(), task(), task(), on_enter(), on_leave() (+13 more)

### Community 2 - "test_core.py"
Cohesion: 0.09
Nodes (21): _client(), handler(), _FakeWmi, _info(), _Obj, _pkg(), _row(), _table_client() (+13 more)

### Community 4 - "updater.py"
Cohesion: 0.15
Nodes (12): task(), apply_and_restart(), check(), _check_signer(), configured(), download(), due(), is_newer() (+4 more)

### Community 5 - "deep_catalog.py"
Cohesion: 0.15
Nodes (9): cab_links_for(), cleanup_package_cache(), _download_and_extract(), fetch_package(), _load_verdicts(), PackageTooLarge, _save_verdict(), verdict_keys() (+1 more)

### Community 6 - "gpu_check.py"
Cohesion: 0.07
Nodes (32): published_driver_names(), select_obsolete(), _version_key(), amd_covered(), amd_installed_version(), check_gpu(), check_gpus(), intel_covered() (+24 more)

### Community 7 - "auto_scan.py"
Cohesion: 0.09
Nodes (20): _command_line(), get_frequency(), last_result(), main(), mark_seen(), next_run(), notification_text(), _powershell() (+12 more)

### Community 8 - "query_ms_catalog"
Cohesion: 0.18
Nodes (7): collect_problem_devices(), installed_driver_date(), is_foreign_architecture(), parse_catalog_date(), parse_wmi_date(), provider_matches(), query_ms_catalog()

### Community 9 - "wu_drivers.py"
Cohesion: 0.13
Nodes (12): catalog_queries(), extract_generic_hwid(), extract_specific_hwid(), windows_update(), find_installed(), install(), merge(), search_drivers() (+4 more)

### Community 10 - "inf_rank.py"
Cohesion: 0.10
Nodes (16): best_match(), best_match_in_package(), _better(), current_os(), _decoration_applies(), feature_score(), _fmt(), Inf (+8 more)

### Community 11 - "Tween"
Cohesion: 0.05
Nodes (17): run(), done(), step(), ease_in_cubic(), ease_in_out_cubic(), ease_out_back(), mix(), _process_start() (+9 more)

### Community 12 - "driver_installer.py"
Cohesion: 0.05
Nodes (42): install_catalog_cab_updates(), dism_component_cleanup(), find_obsolete_driver_packages(), list_driver_packages(), remove_obsolete_driver_packages(), backups_needed_for_undo(), build_entry(), file_hash() (+34 more)

### Community 13 - "test_history.py"
Cohesion: 0.31
Nodes (8): _catalog_entry(), _inf(), test_backups_needed_for_undo(), test_build_entry_tracks_added_removed_and_previous(), test_nvidia_restores_packages_removed_by_installer(), test_undo_plan_refusals(), test_undo_plan_removes_new_package_and_keeps_previous(), test_undo_plan_restores_previous_from_backup_by_hash()

### Community 14 - "test_inf_rank.py"
Cohesion: 0.12
Nodes (11): default_name(), inf(), test_feature_score_from_ddinstall_section(), test_identifier_scores_follow_microsoft_ranges(), test_models_decoration_choice(), test_verify_and_refine_tries_alternative_then_gives_up(), test_search_failure_is_reported(), test_search_skips_ignored() (+3 more)

### Community 19 - "i18n.py"
Cohesion: 0.08
Nodes (16): configured_language(), resolve(), save_language(), windows_language(), another_running(), bring_to_front(), claim(), _k32() (+8 more)

### Community 20 - "diagnostics.py"
Cohesion: 0.27
Nodes (3): export(), _plain(), system_info()

### Community 23 - "ignore_list.py"
Cohesion: 0.17
Nodes (14): add_ignored_update(), add_ignored(), ignore_key(), is_ignored(), keys_for(), load_entries(), load_ignored_updates(), remove_entry() (+6 more)

### Community 24 - "deep_scan_peripherals"
Cohesion: 0.23
Nodes (6): CatalogResult, check_device(), deep_scan_peripherals(), device_ids_map(), scan_problem_devices(), verify_and_refine()

### Community 26 - "test_updater.py"
Cohesion: 0.22
Nodes (3): _client(), test_check_reports_only_newer_versions(), test_download_verifies_hash()

### Community 27 - "prefs.py"
Cohesion: 0.60
Nodes (3): get(), load(), set_value()

## Knowledge Gaps
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `tr()` connect `DriverManagerGUI` to `driver_scanner.py`, `updater.py`, `deep_catalog.py`, `gpu_check.py`, `auto_scan.py`, `query_ms_catalog`, `wu_drivers.py`, `inf_rank.py`, `Tween`, `driver_installer.py`, `i18n.py`, `ModernEventInterceptor`, `deep_scan_peripherals`?**
  _High betweenness centrality (0.267) - this node is a cross-community bridge._
- **Should `DriverManagerGUI` be split into smaller, more focused modules?**
  _Cohesion score 0.0586997685672207 - nodes in this community are weakly interconnected._
- **Why does `DriverManagerGUI` connect `DriverManagerGUI` to `driver_scanner.py`, `Tween`, `driver_installer.py`?**
  _High betweenness centrality (0.077) - this node is a cross-community bridge._
- **Should `test_core.py` be split into smaller, more focused modules?**
  _Cohesion score 0.08961593172119488 - nodes in this community are weakly interconnected._
- **Why does `FastWMI` connect `driver_scanner.py` to `DriverManagerGUI`, `auto_scan.py`, `Tween`, `driver_installer.py`, `config.py`?**
  _High betweenness centrality (0.037) - this node is a cross-community bridge._
- **Should `gpu_check.py` be split into smaller, more focused modules?**
  _Cohesion score 0.06715063520871144 - nodes in this community are weakly interconnected._
- **Should `auto_scan.py` be split into smaller, more focused modules?**
  _Cohesion score 0.09309309309309309 - nodes in this community are weakly interconnected._