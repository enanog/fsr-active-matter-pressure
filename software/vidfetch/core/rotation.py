"""In-plane rotation of each robot from rotation-invariant polar signatures.

Signature: the gray patch is resampled in polar coordinates around the detected centre. A rigid
rotation becomes a circular shift along the angle axis. For two radial bands (battery 0.15-0.70
r_out: metal tab + dots; PCB ring 0.75-0.95 r_out: stand-offs, components) the mean-removed,
std-normalised angular profile is stored as its first K Fourier harmonics (compact: 2x12 complex).

Relative angle between two observations: argmax of the circular cross-correlation
    c(d) = Re sum_b sum_k S2[b,k] conj(S1[b,k]) e^{i k d}
evaluated by inverse FFT on a 0.5 deg grid + parabolic refinement.

Accumulated angle (unbounded, multi-turn), in two stages:
1. Short links: every sample is linked to the samples 1, 2, 4, 8, 16 steps back and all angles are
   solved jointly by weighted least squares (2*pi branches from the incremental chain).
2. Long links (loop closures): links of 32, 64, 128, ... samples (up to the whole record) are added
   level by level. Each level's 2*pi branch comes from the solution with the shorter levels, so the
   prediction error at each new level stays small; links need similarity >= LONG_MIN_QUALITY. Three
   passes re-select the branches with the updated solution, then links with residual > OUTLIER_DEG
   are dropped (the lag-1 chain is always kept) and the system is solved once more.
Why stage 2: short links alone drift. Each frame-to-frame step is biased slightly towards 0 (the
illumination gradient does not rotate with the robot) and the errors add up: on the real videos the
accumulated angle disagreed with a direct comparison of frames 10 min apart by 30-44 deg (median),
>100 deg for 10 % of pairs. Direct comparisons over 5-10 min are consistent to < 1 deg (triangle
closure p90), so they pin the angle down: with stage 2 the 10-min disagreement on held-out frames
is ~0.9 deg (median), ~3 deg (p90).

Sign convention: angles are counter-clockwise as seen on screen (math convention, y up).
"""
from __future__ import annotations

import cv2
import numpy as np
from scipy.sparse import coo_matrix, diags
from scipy.sparse.linalg import cg, spsolve

ANGLE_SAMPLES = 128
HARMONICS = 12
BANDS = ((0.15, 0.70), (0.75, 0.95))
LAGS = (1, 2, 4, 8, 16)
MIN_LINK_QUALITY = 0.80
MAX_LINK_DISAGREEMENT = 30.0   # deg
LONG_FIRST_LAG = 32            # first long-range lag [samples]; doubles up to the record length
LONG_PAIRS = 128               # long lag L: one link every max(1, L // LONG_PAIRS) samples
LONG_MIN_QUALITY = 0.80
LONG_MAX_DISAGREEMENT = 90.0   # deg vs the current solution (branch selection safety)
LONG_PASSES = 3
OUTLIER_DEG = 15.0             # robust pass: residual above which a link is dropped
_GRID = 128                    # coarse correlation grid (2.8 deg), refined by Newton


def signatures(gray: np.ndarray, xs: np.ndarray, ys: np.ndarray, r_out: float) -> np.ndarray:
    """(n, bands, K) complex64 signatures at (xs, ys) in `gray` pixel units."""
    n = len(xs)
    out = np.zeros((n, len(BANDS), HARMONICS), np.complex64)
    R = int(np.ceil(r_out))
    if n == 0 or R < 4:
        return out
    for i, (x, y) in enumerate(zip(xs, ys)):
        if not (np.isfinite(x) and np.isfinite(y)):
            continue
        pol = cv2.warpPolar(gray, (R, ANGLE_SAMPLES), (float(x), float(y)), float(R),
                            cv2.WARP_POLAR_LINEAR).astype(np.float32)  # rows = angle, cols = radius
        for b, (r0, r1) in enumerate(BANDS):
            c0 = int(r0 * R)
            c1 = max(c0 + 1, int(r1 * R))
            band = pol[:, c0:c1]
            prof = (band - band.mean(axis=0, keepdims=True)).mean(axis=1)
            sd = prof.std()
            if sd < 1e-6:
                continue
            prof = (prof - prof.mean()) / sd
            out[i, b] = (np.fft.fft(prof)[1:HARMONICS + 1] / ANGLE_SAMPLES).astype(np.complex64)
    return out


def rel_angle(s1: np.ndarray, s2: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Rotation (deg, CCW on screen, in (-180, 180]) taking s1 -> s2, and normalised similarity.

    c(d) = Re sum_k C_k e^{ikd} is band-limited (k <= K), so a coarse grid locates the peak and
    two Newton steps with the analytic derivatives converge to it exactly.
    """
    s1 = np.asarray(s1, np.complex128)
    s2 = np.asarray(s2, np.complex128)
    K = s1.shape[-1]
    C = (s2 * np.conj(s1)).sum(axis=-2)                      # (..., K)
    spec = np.zeros(C.shape[:-1] + (_GRID,), np.complex128)
    spec[..., 1:K + 1] = C
    c = np.real(np.fft.ifft(spec, axis=-1)) * _GRID
    d = np.argmax(c, axis=-1) * (2 * np.pi / _GRID)
    k = np.arange(1, K + 1)
    for _ in range(2):
        e = C * np.exp(1j * k * d[..., None])
        d1 = np.real((1j * k * e).sum(-1))
        d2 = np.real((-(k ** 2) * e).sum(-1))
        d = d - np.where(d2 < 0, d1 / np.where(d2 == 0, -1, d2), 0.0)
    peak = np.real((C * np.exp(1j * k * d[..., None])).sum(-1))
    polar = (np.degrees(d) + 180.0) % 360.0 - 180.0
    norm = np.sqrt((np.abs(s1) ** 2).sum((-1, -2)) * (np.abs(s2) ** 2).sum((-1, -2)))
    q = peak / np.maximum(norm, 1e-12)
    # warpPolar angle grows clockwise on screen (y down) -> negate for CCW.
    return -polar, q


def _lsq(M: int, i: np.ndarray, j: np.ndarray, m: np.ndarray, w: np.ndarray,
         x0: np.ndarray | None = None) -> np.ndarray:
    """Weighted least squares for theta[j] - theta[i] = m with gauge theta[0] = 0.

    Short lags only: the normal equations are banded and ill-conditioned (chain-like), so a direct
    sparse solve is used (O(M)). With long links the graph diameter collapses and the system is well
    conditioned: Jacobi-preconditioned CG warm-started at the previous solution is ~10x faster than
    the direct solve; it falls back to the direct solve if it does not converge.
    """
    n = len(i)
    r = np.concatenate([np.arange(n), np.arange(n), [n]])
    c = np.concatenate([j, i, [0]])
    v = np.concatenate([np.ones(n), -np.ones(n), [1.0]])
    ww = np.concatenate([w, w, [10.0]])
    A = coo_matrix((v * ww[r], (r, c)), shape=(n + 1, M)).tocsr()
    b = np.concatenate([m * w, [0.0]])
    N = (A.T @ A).tocsc()
    rhs = A.T @ b
    sol, info = None, 1
    if x0 is not None and n and (j - i).max() > LAGS[-1]:
        sol, info = cg(N, rhs, x0=x0, M=diags(1.0 / N.diagonal()), rtol=1e-10, maxiter=3000)
    if info != 0:
        sol = spsolve(N, rhs)
    return sol - sol[0]


def _short_links(sig: np.ndarray) -> tuple[list, np.ndarray, np.ndarray]:
    """Lag 1, 2, 4, 8, 16 links with branches from the incremental chain. Returns (links, chain, q1)."""
    M = len(sig)
    inc, q1 = rel_angle(sig[:-1], sig[1:])
    theta0 = np.concatenate([[0.0], np.cumsum(inc)])
    links = []
    for L in LAGS:
        if L >= M:
            break
        if L == 1:
            m, q = inc, q1
            ok = np.ones(M - 1, bool)  # keep the chain connected
        else:
            m, q = rel_angle(sig[:-L], sig[L:])
            pred = theta0[L:] - theta0[:-L]
            m = m + 360.0 * np.round((pred - m) / 360.0)
            ok = (q >= MIN_LINK_QUALITY) & (np.abs(m - pred) < MAX_LINK_DISAGREEMENT)
        idx = np.flatnonzero(ok)
        links.append((idx, idx + L, m[idx], np.sqrt(np.clip(q[idx], 0.05, None))))
    return links, theta0, q1


def _cat(links: list) -> tuple[np.ndarray, ...]:
    return tuple(np.concatenate([lk[n] for lk in links]) for n in range(4))


def solve_angles(sig: np.ndarray, long_range: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """Unbounded CCW angle (deg, first sample = 0) for a time-ordered signature sequence (M, b, K).

    Returns (theta, link_quality) where link_quality is the similarity with the previous sample.
    long_range=False reproduces the previous short-links-only solution (for comparisons).
    """
    M = len(sig)
    if M == 0:
        return np.zeros(0), np.zeros(0)
    if M == 1:
        return np.zeros(1), np.ones(1)
    short, _, q1 = _short_links(sig)
    theta = _lsq(M, *_cat(short))
    if M <= LONG_FIRST_LAG or not long_range:
        return theta, np.concatenate([[1.0], q1])
    long_links: list = []
    for _ in range(LONG_PASSES):
        long_links = []
        L = LONG_FIRST_LAG
        while L < M:
            ii = np.arange(0, M - L, max(1, L // LONG_PAIRS))
            m, q = rel_angle(sig[ii], sig[ii + L])
            pred = theta[ii + L] - theta[ii]
            m = m + 360.0 * np.round((pred - m) / 360.0)
            ok = (q >= LONG_MIN_QUALITY) & (np.abs(m - pred) < LONG_MAX_DISAGREEMENT)
            if ok.any():
                long_links.append((ii[ok], ii[ok] + L, m[ok], np.sqrt(np.clip(q[ok], 0.05, None))))
                theta = _lsq(M, *_cat(short + long_links), x0=theta)
            L *= 2
    i, j, m, w = _cat(short + long_links)
    keep = (np.abs(theta[j] - theta[i] - m) < OUTLIER_DEG) | (j - i == 1)
    theta = _lsq(M, i[keep], j[keep], m[keep], w[keep], x0=theta)
    return theta, np.concatenate([[1.0], q1])
