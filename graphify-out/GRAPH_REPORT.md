# Graph Report - DriverManager  (2026-11-09)

## Corpus Check
- 31 files · ~34,038 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 5 file(s) not represented in the graph (top: (none) 2, .bat 1, .ico 1)

## Summary
- 672 nodes · 1689 edges · 26 communities (18 shown, 8 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 55 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- build.py
- DriverManagerGUI
- test_core.py
- driver_scanner.py
- updater.py
- single_instance.py
- gpu_check.py
- auto_scan.py
- gui.py
- deep_catalog.py
- inf_rank.py
- Tween
- driver_installer.py
- test_history.py
- test_inf_rank.py
- config.py
- test_i18n.py
- diagnostics.py
- ModernEventInterceptor
- json
- i18n.py

## God Nodes (most connected - your core abstractions)
1. `tr()` - 110 edges
2. `DriverManagerGUI` - 70 edges
3. `FastWMI` - 21 edges
4. `main()` - 21 edges
5. `backup_current_drivers()` - 20 edges
6. `deep_scan_peripherals()` - 18 edges
7. `install_catalog_cab_updates()` - 17 edges
8. `verify_candidate()` - 16 edges
9. `Tween` - 15 edges
10. `snapshot_infs()` - 15 edges

## Surprising Connections (you probably didn't know these)
- `write_manifest()` --calls--> `release_asset_url()`  [INFERRED]
  build.py → src/config.py
- `DriverManagerGUI` --uses--> `FastWMI`  [INFERRED]
  src/gui.py → src/wmi_fast.py
- `run_scan()` --calls--> `FastWMI`  [EXTRACTED]
  src/auto_scan.py → src/wmi_fast.py
- `task()` --calls--> `FastWMI`  [EXTRACTED]
  src/gui.py → src/wmi_fast.py
- `main()` --calls--> `FastWMI`  [EXTRACTED]
  src/main.py → src/wmi_fast.py

## Import Cycles
- None detected.

## Communities (26 total, 8 thin omitted)

### Community 0 - "build.py"
Cohesion: 0.20
Nodes (7): _arg(), main(), make_icon(), pyinstaller(), version_file(), write_manifest(), release_asset_url()

### Community 1 - "DriverManagerGUI"
Cohesion: 0.06
Nodes (17): clean_gpu_shader_cache(), create_system_restore_point(), dark_title_bar(), DriverManagerGUI, work(), task(), task(), toggle() (+9 more)

### Community 2 - "test_core.py"
Cohesion: 0.09
Nodes (21): _client(), handler(), _FakeWmi, _info(), _Obj, _pkg(), _row(), _table_client() (+13 more)

### Community 4 - "updater.py"
Cohesion: 0.09
Nodes (16): subject_organization(), task(), apply_and_restart(), check(), _check_signer(), configured(), download(), due() (+8 more)

### Community 5 - "single_instance.py"
Cohesion: 0.21
Nodes (7): another_running(), bring_to_front(), claim(), _k32(), request_focus(), watch(), check()

### Community 6 - "gpu_check.py"
Cohesion: 0.07
Nodes (29): amd_covered(), amd_installed_version(), check_gpu(), check_gpus(), intel_covered(), is_newer(), normalize_name(), nv_date_to_iso() (+21 more)

### Community 7 - "auto_scan.py"
Cohesion: 0.10
Nodes (18): _command_line(), get_frequency(), last_result(), main(), mark_seen(), next_run(), notification_text(), _powershell() (+10 more)

### Community 8 - "gui.py"
Cohesion: 0.11
Nodes (4): _process_start(), _selftest_done(), _system_animations_enabled(), windows_uses_dark()

### Community 9 - "deep_catalog.py"
Cohesion: 0.05
Nodes (40): add_ignored_update(), cab_links_for(), catalog_queries(), CatalogResult, check_device(), cleanup_package_cache(), collect_problem_devices(), deep_scan_peripherals() (+32 more)

### Community 10 - "inf_rank.py"
Cohesion: 0.10
Nodes (16): best_match(), best_match_in_package(), _better(), current_os(), _decoration_applies(), feature_score(), _fmt(), Inf (+8 more)

### Community 11 - "Tween"
Cohesion: 0.07
Nodes (17): run(), done(), step(), on_enter(), on_leave(), on_enter(), on_leave(), on_release() (+9 more)

### Community 12 - "driver_installer.py"
Cohesion: 0.05
Nodes (41): dism_component_cleanup(), find_obsolete_driver_packages(), list_driver_packages(), remove_obsolete_driver_packages(), select_obsolete(), _version_key(), backups_needed_for_undo(), file_hash() (+33 more)

### Community 13 - "test_history.py"
Cohesion: 0.31
Nodes (8): _catalog_entry(), _inf(), test_backups_needed_for_undo(), test_build_entry_tracks_added_removed_and_previous(), test_nvidia_restores_packages_removed_by_installer(), test_undo_plan_refusals(), test_undo_plan_removes_new_package_and_keeps_previous(), test_undo_plan_restores_previous_from_backup_by_hash()

### Community 14 - "test_inf_rank.py"
Cohesion: 0.24
Nodes (5): inf(), test_feature_score_from_ddinstall_section(), test_identifier_scores_follow_microsoft_ranges(), test_models_decoration_choice(), test_verify_and_refine_tries_alternative_then_gives_up()

### Community 19 - "test_i18n.py"
Cohesion: 0.22
Nodes (5): fields(), test_every_text_has_an_english_translation(), test_no_unused_translations(), test_placeholders_match(), tr_keys()

### Community 20 - "diagnostics.py"
Cohesion: 0.25
Nodes (4): default_name(), export(), _plain(), system_info()

### Community 23 - "json"
Cohesion: 0.10
Nodes (19): build_entry(), add_ignored(), keys_for(), load_entries(), remove_entry(), _save(), wu_key(), get() (+11 more)

### Community 24 - "i18n.py"
Cohesion: 0.29
Nodes (4): configured_language(), resolve(), save_language(), windows_language()

## Knowledge Gaps
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `tr()` connect `DriverManagerGUI` to `driver_scanner.py`, `updater.py`, `gpu_check.py`, `auto_scan.py`, `gui.py`, `deep_catalog.py`, `inf_rank.py`, `driver_installer.py`, `ModernEventInterceptor`, `i18n.py`?**
  _High betweenness centrality (0.270) - this node is a cross-community bridge._
- **Should `DriverManagerGUI` be split into smaller, more focused modules?**
  _Cohesion score 0.06360100663463739 - nodes in this community are weakly interconnected._
- **Why does `DriverManagerGUI` connect `DriverManagerGUI` to `gui.py`, `driver_scanner.py`, `Tween`, `driver_installer.py`?**
  _High betweenness centrality (0.082) - this node is a cross-community bridge._
- **Should `test_core.py` be split into smaller, more focused modules?**
  _Cohesion score 0.08961593172119488 - nodes in this community are weakly interconnected._
- **Why does `FastWMI` connect `driver_scanner.py` to `DriverManagerGUI`, `auto_scan.py`, `gui.py`, `driver_installer.py`, `config.py`?**
  _High betweenness centrality (0.040) - this node is a cross-community bridge._
- **Should `updater.py` be split into smaller, more focused modules?**
  _Cohesion score 0.0873015873015873 - nodes in this community are weakly interconnected._
- **Should `gpu_check.py` be split into smaller, more focused modules?**
  _Cohesion score 0.07294117647058823 - nodes in this community are weakly interconnected._