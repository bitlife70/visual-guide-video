"""시간 리매핑: 원본 시각(ts) ↔ 출력 시각(t).

timeline.py 의 모든 시각은 '원본 영상 시각'으로 적는다. 엔진이 TRIM·SPEED·FREEZE 를 반영해 출력 시각으로 바꾼다.
  TRIM   = (시작, 끝)                       원본에서 쓸 구간
  SPEED  = [(t0, t1, 배율[, 라벨])]         0.3 = 슬로모션, 2.0 = 빨리감기 (가장자리는 부드럽게 램프)
  FREEZE = [(t, 정지 길이[, 라벨])]         t 에서 화면을 멈추고 정지 길이(초)만큼 출력에 끼워 넣음

구간 (t0, t1) 을 출력으로 바꿀 때 시작은 왼쪽 극한, 끝은 오른쪽 극한을 쓴다.
→ 정지 시각 tf 에 대해 (tf, tf) 구간은 '정지된 동안'이 된다.
"""
import numpy as np


class Remap:
    def __init__(self, t_start, t_end, speed=(), freeze=(), step=1 / 1000):
        self.t_start, self.t_end = float(t_start), float(t_end)
        ts = np.arange(self.t_start, self.t_end + step / 2, step)
        rate = np.ones_like(ts)
        for sp in speed:
            a, b, r = float(sp[0]), float(sp[1]), float(sp[2])
            ramp = min(0.25, (b - a) / 4)
            m = (ts >= a) & (ts <= b)
            if not m.any():
                continue
            u = np.minimum((ts[m] - a) / ramp, (b - ts[m]) / ramp) if ramp > 0 else np.ones(m.sum())
            k = np.clip(u, 0, 1)
            k = k * k * (3 - 2 * k)  # smoothstep
            rate[m] = 1 + (r - 1) * k
        dtau = np.diff(ts) / ((rate[1:] + rate[:-1]) / 2)
        tau = np.concatenate([[0.0], np.cumsum(dtau)])
        # 정지: 해당 원본 시각에 출력 시간을 끼워 넣음
        self.freezes = []
        for fz in sorted(freeze, key=lambda f: f[0]):
            tf, hold = float(fz[0]), float(fz[1])
            if not (self.t_start <= tf <= self.t_end):
                continue
            i = int(np.searchsorted(ts, tf))
            tau = np.concatenate([tau[:i], [np.interp(tf, ts, tau)], [np.interp(tf, ts, tau) + hold], tau[i:] + hold])
            ts = np.concatenate([ts[:i], [tf, tf], ts[i:]])
            self.freezes.append((tf, hold))
        self.ts, self.tau = ts, tau
        self.duration = float(tau[-1])
        self.identity = not speed and not self.freezes

    # 출력 시각 → 원본 시각
    def src(self, t):
        return float(np.interp(t, self.tau, self.ts))

    def src_array(self, t):
        return np.interp(t, self.tau, self.ts)

    # 원본 시각 → 출력 시각 (side='left' 는 정지 직전, 'right' 는 정지 직후)
    def out(self, ts, side="left"):
        x = min(max(float(ts), self.t_start), self.t_end)
        n = len(self.ts)
        if side == "left":  # 같은 원본 시각이 여러 번(정지) 있으면 첫 번째
            i = min(int(np.searchsorted(self.ts, x, "left")), n - 1)
            if self.ts[i] == x or i == 0:
                return float(self.tau[i])
            a, b = i - 1, i
        else:  # 마지막 번째
            i = max(int(np.searchsorted(self.ts, x, "right")) - 1, 0)
            if self.ts[i] == x or i == n - 1:
                return float(self.tau[i])
            a, b = i, i + 1
        u = (x - self.ts[a]) / (self.ts[b] - self.ts[a])
        return float(self.tau[a] + (self.tau[b] - self.tau[a]) * u)

    def span(self, t0, t1):
        return self.out(t0, "left"), self.out(t1, "right")

    def rate_at(self, t, eps=1 / 120):
        """출력 시각 t 에서의 재생 배율 (dts/dt). 0 이면 정지."""
        return (self.src(t + eps) - self.src(max(0.0, t - eps))) / (2 * eps)
