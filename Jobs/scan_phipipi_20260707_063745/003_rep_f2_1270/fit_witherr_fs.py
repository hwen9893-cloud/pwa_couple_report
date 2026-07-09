#!/usr/bin/env python3
import csv
import json
import os

def _outpath(fname):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
import time
from pprint import pprint

# avoid using Xwindow
import matplotlib
matplotlib.use("agg")

import tensorflow as tf

# keep imports so custom models in yaml can still be resolved
from tf_pwa.amp import simple_resonance  # noqa: F401
from tf_pwa.config_loader import ConfigLoader, MultiConfig
from tf_pwa.experimental import extra_amp, extra_data  # noqa: F401
from tf_pwa.utils import error_print, tuple_table


def json_print(dic):
    """print parameters as json"""
    s = json.dumps(dic, indent=2)
    print(s, flush=True)


def save_frac_csv(file_name, fit_frac):
    table = tuple_table(fit_frac)
    with open(file_name, "w") as f:
        f_csv = csv.writer(f, delimiter="\t")
        f_csv.writerows(row[1:] for row in table[1:])


def write_run_point():
    """write time as a point of fit start"""
    with open(".run_start", "w") as f:
        localtime = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(time.time())
        )
        f.write(localtime)


def load_single_config(config_file):
    print(f"[INFO] load config: {config_file}", flush=True)
    return ConfigLoader(config_file)


def inspect_common_params(configs, only_show_prod=True):
    """
    Print parameter names shared across multiple configs.
    For φhh / ωhh coupled-channel analyses there are two natural sharing classes:
      1. production-side chain coefficients (these usually do NOT overlap because
         the intermediate states differ between KK and ππ channels);
      2. internal Flatte couplings (g_0, g_1 etc.) — the actual coupled-channel
         "coupling point" between KK and ππ.
    We print both so that the user can confirm at a glance that the joint fit
    really is doing coupled-channel physics.
    """
    if len(configs) < 2:
        return

    param_sets = []
    for i, c in enumerate(configs):
        params_i = set(c.get_params().keys())
        param_sets.append(params_i)
        print(f"[INFO] channel {i} number of params: {len(params_i)}", flush=True)

    common = sorted(set.intersection(*param_sets))

    prod_common = [p for p in common if p.startswith("Jpsi->")]
    flatte_common = [p for p in common if "_flatte_" in p]
    other_common = [
        p for p in common if p not in prod_common and p not in flatte_common
    ]

    print(
        f"[INFO] shared params: total={len(common)} "
        f"prod={len(prod_common)} flatte={len(flatte_common)} other={len(other_common)}",
        flush=True,
    )
    if flatte_common:
        print("[INFO] Flatte-coupling shared (real coupled-channel point):", flush=True)
        for p in flatte_common:
            print("    [flatte]", p, flush=True)
    if not only_show_prod:
        if prod_common:
            print("[INFO] production-side shared:", flush=True)
            for p in prod_common:
                print("    [prod]  ", p, flush=True)
        if other_common:
            print("[INFO] other shared:", flush=True)
            for p in other_common:
                print("    [other] ", p, flush=True)


def load_joint_config(config_files, total_same=False, inspect=True):
    """
    Load multiple ConfigLoader objects first, inspect common parameter names,
    then build a MultiConfig using the same yaml list.

    We keep total_same=False by default, because the goal is to share only
    production-side common parameters, not the full-chain total coefficients.
    """
    config_files = [i.strip() for i in config_files if i.strip()]
    cfgs = [load_single_config(f) for f in config_files]

    if inspect:
        inspect_common_params(cfgs, only_show_prod=True)

    print(f"[INFO] build MultiConfig with total_same={total_same}", flush=True)
    # Keep the official MultiConfig workflow
    return MultiConfig(config_files, total_same=total_same)


def load_config(config_file="config.yml", total_same=False, inspect=True):
    config_files = [i.strip() for i in config_file.split(",") if i.strip()]
    if len(config_files) == 1:
        return load_single_config(config_files[0])
    return load_joint_config(config_files, total_same=total_same, inspect=inspect)


def fit(config, init_params="", method="BFGS", loop=1, maxiter=500,
        batch_fit=65000, batch_err=13000):
    """
    simple fit script for one or multiple channels
    """
    _ = config.get_all_data()

    if isinstance(config, MultiConfig):
        print(
            f"[INFO] running JOINT fit with {len(config.configs)} channels",
            flush=True,
        )
    else:
        print("[INFO] running SINGLE-CHANNEL fit", flush=True)

    fit_results = []
    for i in range(loop):
        print(f"\n========== Fit loop {i+1}/{loop} ==========", flush=True)

        # set initial parameters if provided
        if init_params and config.set_params(init_params):
            print(f"using {init_params}", flush=True)
        else:
            print("using RANDOM parameters", flush=True)

        try:
            fit_result = config.fit(
                batch=batch_fit, method=method, maxiter=maxiter
            )
        except KeyboardInterrupt:
            config.save_params(_outpath("break_params.json"))
            raise
        except Exception as e:
            print("[ERROR]", e, flush=True)
            config.save_params(_outpath("break_params.json"))
            raise

        fit_results.append(fit_result)

        try:
            config.reinit_params()
        except Exception as e:
            print("[WARN] reinit_params failed:", e, flush=True)

    # select best result
    fit_result = fit_results.pop()
    for i in fit_results:
        if i.success:
            if (not fit_result.success) or (fit_result.min_nll > i.min_nll):
                fit_result = i

    config.set_params(fit_result.params)
    json_print(fit_result.params)
    fit_result.save_as(_outpath("final_params.json"))

    # calculate parameters error
    # calculate parameters error
    if maxiter != 0:
        import numpy as np

        # ── Hessian 误差估计（带奇异矩阵保护）──────────────────────────────
        fit_error = {}
        try:
            fit_error = config.get_params_error(fit_result, batch=batch_err)

        except np.linalg.LinAlgError as e:
            print(f"\n[WARN] Hessian inversion failed: {e}", flush=True)
            print("[WARN] Falling back to pseudo-inverse (pinv). "
                  "Errors in singular directions will be NaN/inf.", flush=True)

            # ── 1. 诊断：打印特征值谱，定位奇异方向 ─────────────────────────
            try:
                # 重新计算 Hessian（不做 inv），借助内部接口
                from tf_pwa.applications import cal_hesse_error
                import functools

                # 拿到 NLL 函数和当前参数
                amp = config.get_amplitude() if hasattr(config, "get_amplitude") \
                      else None
                nll_fn = getattr(config, "_get_nll_grad", None)

                # 直接访问 multi_config 已缓存的 Hessian（若存在）
                h_raw = getattr(config, "_last_hessian", None)

                if h_raw is not None:
                    eigvals, eigvecs = np.linalg.eigh(h_raw)
                    print("\n[DIAG] Hessian eigenvalue spectrum (sorted):")
                    for idx, ev in enumerate(eigvals):
                        marker = " *** SINGULAR" if abs(ev) < 1e-6 * abs(eigvals).max() else ""
                        print(f"  [{idx:3d}]  {ev:+.6e}{marker}", flush=True)
                    cond = abs(eigvals[-1] / eigvals[0]) if eigvals[0] != 0 else np.inf
                    print(f"[DIAG] Condition number: {cond:.3e}", flush=True)

                    # 找出奇异方向对应的参数
                    param_names = list(fit_result.params.keys())
                    threshold = 1e-6 * abs(eigvals).max()
                    singular_dirs = np.where(abs(eigvals) < threshold)[0]
                    if len(singular_dirs):
                        print(f"[DIAG] {len(singular_dirs)} singular direction(s):", flush=True)
                        for sd in singular_dirs:
                            evec = eigvecs[:, sd]
                            top3 = np.argsort(abs(evec))[-3:][::-1]
                            top3_str = ", ".join(
                                f"{param_names[j] if j < len(param_names) else j}"
                                f"(w={evec[j]:.3f})"
                                for j in top3
                            )
                            print(f"  eigenvalue={eigvals[sd]:.2e}  →  {top3_str}", flush=True)
                else:
                    print("[DIAG] _last_hessian not cached, cannot show eigenvalue details.",
                          flush=True)
            except Exception as diag_err:
                print(f"[DIAG] Eigenvalue diagnosis failed: {diag_err}", flush=True)

            # ── 2. 用 pinv 构造近似误差 ──────────────────────────────────────
            try:
                from tf_pwa.applications import cal_hesse_error as _cal_he
                import unittest.mock as _mock

                # 用 monkeypatch 方式把 np.linalg.inv 替换为 pinv
                _orig_inv = np.linalg.inv

                def _pinv_fallback(m):
                    try:
                        return _orig_inv(m)
                    except np.linalg.LinAlgError:
                        print("[WARN] using pinv for singular Hessian block", flush=True)
                        return np.linalg.pinv(m, rcond=1e-10)

                # 打补丁并重新调用
                np.linalg.inv = _pinv_fallback
                try:
                    fit_error = config.get_params_error(fit_result, batch=batch_err)
                finally:
                    np.linalg.inv = _orig_inv   # 一定恢复原函数

                print("[INFO] pinv fallback succeeded, errors in singular directions "
                      "may be unreliable.", flush=True)

            except Exception as pinv_err:
                print(f"[ERROR] pinv fallback also failed: {pinv_err}", flush=True)
                print("[INFO] Saving fit result WITHOUT parameter errors.", flush=True)

        # ── 保存结果（无论误差估计是否成功）────────────────────────────────
        if fit_error:
            fit_result.set_error(fit_error)
        fit_result.save_as(_outpath("final_params.json"))

        inv_he = getattr(config, "inv_he", None)
        if inv_he is not None:
            np.savetxt(_outpath("error_matrix.txt"), inv_he)
        else:
            print("[WARN] inv_he not available, skip writing error_matrix.txt",
                  flush=True)
        if inv_he is not None:
            cond = np.linalg.cond(inv_he)
            if cond > 1e12:
                print(f"[WARN] Hessian near-singular (condition number = {cond:.2e})")

        if fit_error:
            pprint(fit_error)

        print("\n########## fit results:")
        print("Fit status: ", fit_result.success)
        print("Minimal -lnL = ", fit_result.min_nll)
        for k, v in config.get_params().items():
            print(k, error_print(v, fit_error.get(k, None)))

    return fit_result


def _safe_get_phsp_noeff(config_i):
    """
    Return phsp_noeff dataset if the config provides one and the file exists,
    otherwise return None. Useful when phsp_noeff path is not yet finalized
    (e.g. φπ⁺π⁻ channel).
    """
    try:
        return config_i.get_phsp_noeff()
    except Exception as e:
        print(f"[WARN] phsp_noeff unavailable, skip fit fractions: {e}", flush=True)
        return None


def write_some_results(config, fit_result, save_root=False):
    """
    single-channel post-processing
    """
    config.plot_partial_wave(
        fit_result,
        plot_pull=True,
        save_root=save_root,
        single_legend=True,
        chains_id_method="res",
    )

    phsp_noeff = _safe_get_phsp_noeff(config)
    if phsp_noeff is None:
        print("[WARN] skip fit fraction calculation (no phsp_noeff)", flush=True)
        return

    fit_frac, err_frac = config.cal_fitfractions(
        {},
        phsp_noeff,
        exclude_res=["Lmdc"],
    )

    print("########## fit fractions")
    fit_frac_string = ""
    for i in fit_frac:
        if isinstance(i, tuple):
            name = "{}x{}".format(*i)
        else:
            name = i
        fit_frac_string += "{} {}\n".format(
            name, error_print(fit_frac[i], err_frac.get(i, None))
        )
    print(fit_frac_string)

    save_frac_csv("fit_frac.csv", fit_frac)
    save_frac_csv("fit_frac_err.csv", err_frac)


def write_some_results_combine(config, fit_result, save_root=False):
    """
    joint-fit post-processing
    """
    from tf_pwa.applications import fit_fractions

    os.makedirs("figure", exist_ok=True)

    for i, c in enumerate(config.configs):
        c.plot_partial_wave(
            fit_result,
            prefix=f"figure/s{i}_",
            plot_pull=True,
            save_root=save_root,
            single_legend=True,
            chains_id_method="res",
        )

    # 当 maxiter=0（跳过误差计算）或 Hessian 反演失败时，inv_he 可能不存在 →
    # fit_fractions 在 inv_he=None 时只算中心值不算误差，这里做兜底。
    inv_he = getattr(config, "inv_he", None)
    if inv_he is None:
        print(
            "[WARN] inv_he not available (maxiter=0 or Hessian inversion failed) "
            "→ fit fractions will be computed without errors.",
            flush=True,
        )

    for it, config_i in enumerate(config.configs):
        print(f"########## fit fractions channel {it}:")
        mcdata = _safe_get_phsp_noeff(config_i)
        if mcdata is None:
            print(
                f"[WARN] skip fit fractions for channel {it} (no phsp_noeff)",
                flush=True,
            )
            continue
        fit_frac, err_frac = fit_fractions(
            config_i.get_amplitude(),
            mcdata,
            inv_he,
            fit_result.params,
        )
        fit_frac_string = ""
        for i in fit_frac:
            if isinstance(i, tuple):
                name = "{}x{}".format(*i)
            else:
                name = i
            fit_frac_string += "{} {}\n".format(
                name, error_print(fit_frac[i], err_frac.get(i, None))
            )
        print(fit_frac_string)
        save_frac_csv(f"fit_frac_channel{it}.csv", fit_frac)
        save_frac_csv(f"fit_frac_channel{it}_err.csv", err_frac)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="TFPWA joint-fit script")
    parser.add_argument(
        "--no-GPU", action="store_false", default=True, dest="has_gpu"
    )
    parser.add_argument("-c", "--config", default="config.yml", dest="config")
    parser.add_argument(
        "-i", "--init_params", default="", dest="init",
        help="optional initial parameter file; empty (default) = random initialisation"
    )
    parser.add_argument("-m", "--method", default="BFGS", dest="method")
    parser.add_argument("-l", "--loop", type=int, default=1, dest="loop")
    parser.add_argument(
        "-x", "--maxiter", type=int, default=2000, dest="maxiter"
    )
    parser.add_argument("-r", "--save_root", default=False, dest="save_root")
    parser.add_argument(
        "--total-same", action="store_true", default=False, dest="total_same"
    )
    parser.add_argument(
        "--no-inspect", action="store_false", default=True, dest="inspect"
    )
    parser.add_argument(
        "--batch-fit", type=int, default=95000, dest="batch_fit"
    )
    parser.add_argument(
        "--batch-err", type=int, default=45000, dest="batch_err"
    )

    results = parser.parse_args()

    devices = "/device:GPU:0" if results.has_gpu else "/device:CPU:0"

    with tf.device(devices):
        config = load_config(
            results.config,
            total_same=results.total_same,
            inspect=results.inspect,
        )

        fit_result = fit(
            config,
            init_params=results.init,
            method=results.method,
            loop=results.loop,
            maxiter=results.maxiter,
            batch_fit=results.batch_fit,
            batch_err=results.batch_err,
        )

        if isinstance(config, ConfigLoader):
            write_some_results(
                config,
                fit_result,
                save_root=results.save_root,
            )
        else:
            write_some_results_combine(
                config,
                fit_result,
                save_root=results.save_root,
            )


if __name__ == "__main__":
    write_run_point()
    main()
