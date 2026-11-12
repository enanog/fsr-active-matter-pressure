function [tau, msd, alfa] = desplazamiento_cuadratico(D, tau_max_s, n_puntos)
% DESPLAZAMIENTO_CUADRATICO  Mean square displacement <|r(t + tau) - r(t)|^2> over robots and t [mm^2],
% at log-spaced lags up to tau_max_s (default: min(1/4 of the trial, 20 min)), as comparar_ensayos.py.
%   alfa: slope of log MSD vs log tau between 1 and 20 s (1 = diffusive, 2 = ballistic)
    dif = diff(D.t);
    salto = dif > 1.5 * median(dif);                % video gap (split recording)
    seg = [0; cumsum(salto(:))];                    % segment of every frame
    dt = mean(dif(~salto));
    F = numel(D.t);
    if nargin < 2 || isempty(tau_max_s), tau_max_s = min(F / 4 * dt, 1200); end
    if nargin < 3, n_puntos = 40; end
    L_max = max(1, floor(tau_max_s / dt));
    lags = unique(round(logspace(0, log10(L_max), n_puntos)));
    msd = nan(numel(lags), 1);
    for k = 1:numel(lags)
        L = lags(k);
        d2 = (D.X(L + 1:end, :) - D.X(1:end - L, :)) .^ 2 + (D.Y(L + 1:end, :) - D.Y(1:end - L, :)) .^ 2;
        cruza = seg(L + 1:end) ~= seg(1:end - L);   % pairs across a video gap
        d2(cruza, :) = NaN;
        msd(k) = mean(d2(isfinite(d2)));
    end
    tau = lags(:) * dt;
    ajuste = tau >= 1 & tau <= 20 & msd > 0;
    alfa = NaN;
    if nnz(ajuste) > 2
        c = polyfit(log(tau(ajuste)), log(msd(ajuste)), 1);
        alfa = c(1);
    end
end
