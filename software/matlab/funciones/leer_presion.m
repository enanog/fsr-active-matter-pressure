function P = leer_presion(raiz, codigo)
% LEER_PRESION  Sensor log R_<code>.csv processed exactly as FSRScope does; [] if there is none.
%   P.t        uniform time grid [sensor s, t0 = first valid row], step P.paso (0.05 s by default)
%   P.G        conductance on the grid [uS] = ADC (linearly resampled) * P.K
%   P.mascara  samples that enter the statistics: inside the crop, outside the excluded spans and,
%              if FSRScope says so, not saturated (use presion_valida(P) to get G with NaN outside)
%   P.sat      ADC at full scale (G is only a lower bound there)
%   P.K        [uS/count]: firmware factor (calibration 'auto') or circuit parameters ('manual')
%   P.offset   [s] video <-> sensor: t_sensor = offset + t_video (end of the LED pulse or manual)
%   P.deltaT_fijo, P.deltaT_max, P.clases: FSRScope analysis settings of the trial
%   P.r_feedback  [ohm] feedback resistor equivalent to P.K (with the V_EXC of the settings)
% Settings come from datos/presion/config/<code>.json (written by FSRScope); defaults otherwise.
% R_FEEDBACK: datos/presion/calibracion.csv (the list) > manual calibration of FSRScope > firmware factor.
    P = [];
    f = fullfile(raiz, 'datos', 'presion', 'crudos', ['R_' codigo '.csv']);
    if ~isfile(f), return; end
    T = leer_csv(f, {'timestamp(ms)', 'led', 'g', 'g_us', 'r', 'r_ohm', 'adc_raw', 'adc', 'sync', ...
                     'clipsat', 'n'});
    t = T.timestamp_ms_;
    adc = T.adc_raw;
    if all(isnan(adc)), adc = T.adc; end
    if all(isnan(adc)), warning('%s: sin columna ADC.', codigo); return; end

    % --- time: units, junk rows, t0 (same rules as comun/log_io.py) ---
    dts = diff(t(isfinite(t)));  dts = dts(dts > 0);
    if ~isempty(dts) && median(dts) > 5, t = t / 1000; end            % real milliseconds
    med = mediana_movil(t, 25);
    t(isfinite(t) & abs(t - med) > 5) = NaN;                           % junk rows (absurd time)
    t = t - t(find(isfinite(t), 1));                                   % t0 = first valid row
    led_off = NaN;
    on = find(T.led == 1);
    if numel(on) >= 3
        br = find(diff(on) > 1, 1);
        if ~isempty(br), on = on(1:br); end
        led_off = t(on(end));
    end
    fila = isnan(T.sync) & isfinite(t) & isfinite(adc);                % no SYNC marker rows
    G_fw = T.g;  if all(isnan(G_fw)), G_fw = T.g_us; end
    R_fw = T.r;  if all(isnan(R_fw)), R_fw = T.r_ohm; end
    [t, iu] = unique(t(fila));
    sel = find(fila);  sel = sel(iu);
    adc = adc(sel);  G_fw = G_fw(sel);  R_fw = R_fw(sel);
    full = (T.clipsat(sel) >= T.n(sel)) & (T.n(sel) > 0);              % every oversampled reading clipped

    % --- settings of the trial (FSRScope) ---
    J = struct();
    cfg = fullfile(raiz, 'datos', 'presion', 'config', [codigo '.json']);
    if isfile(cfg), J = jsondecode(fileread(cfg)); end
    cal = struct('mode', 'auto', 'v_ref', 3.3, 'v_exc', 0.7534, 'r_feedback', 1000, 'adc_fs', 1023);
    an = struct('step_s', 0.05, 'deltaT_fixed_s', 2.5, 'deltaT_max_s', 15, 't_start', [], 't_end', [], ...
                'exclusions', [], 'exclude_saturated', false, 'hist_bins', 120);
    cal = completar(cal, J, 'calibration');
    an = completar(an, J, 'analysis');
    [r_lista, nota_lista] = r_feedback_lista(raiz, codigo);
    if isfinite(r_lista)
        cal.mode = 'lista';  cal.r_feedback = r_lista;
    end

    % --- conductance factor: firmware median G/ADC (auto) or circuit parameters ---
    K_fw = NaN;
    ok = adc > 0.05;
    if any(isfinite(G_fw))
        ok = ok & isfinite(G_fw) & G_fw > 0;
        if nnz(ok) > 10, K_fw = median(G_fw(ok) ./ adc(ok)); end
    elseif any(isfinite(R_fw))
        ok = ok & isfinite(R_fw) & R_fw > 0;
        if nnz(ok) > 10, K_fw = median(1e6 ./ (R_fw(ok) .* adc(ok))); end
    end
    K_par = cal.v_ref * 1e6 / (cal.adc_fs * cal.v_exc * cal.r_feedback);
    if strcmp(cal.mode, 'auto') && isfinite(K_fw)
        K = K_fw;  origen_K = 'firmware';
    else
        K = K_par;
        if strcmp(cal.mode, 'lista')
            origen_K = 'calibracion.csv';
        else
            origen_K = 'FSRScope (manual)';
        end
        if isfinite(K_fw) && abs(K / K_fw - 1) > 0.02
            fprintf('  %s: R_FEEDBACK = %g ohm (%s) -> G x%.3g respecto del firmware%s\n', codigo, ...
                    cal.r_feedback, origen_K, K / K_fw, sufijo(nota_lista));
        end
    end
    r_eq = cal.v_ref * 1e6 / (cal.adc_fs * cal.v_exc * K);

    % --- uniform grid, saturation, analysis mask ---
    paso = an.step_s;
    n = floor((t(end) - t(1)) / paso) + 1;
    tu = t(1) + (0:n - 1)' * paso;
    adc_u = interp1(t, adc, tu, 'linear');
    adc_u(tu > t(end)) = adc(end);                                     % clamp at the edges, as np.interp
    adc_u(tu < t(1)) = adc(1);
    idx = interp1(t, (1:numel(t))', tu, 'next');                       % first raw row at/after each grid time
    idx(isnan(idx)) = numel(t);
    sat = adc(idx) >= cal.adc_fs - 0.5;
    if any(T.n > 0), sat = sat | full(idx); end
    m = true(n, 1);
    if ~isempty(an.t_start), m = m & tu >= an.t_start; end
    if ~isempty(an.t_end), m = m & tu <= an.t_end; end
    if ~isempty(an.exclusions)
        ex = reshape(an.exclusions, [], 2);
        for j = 1:size(ex, 1)
            m = m & ~(tu >= min(ex(j, :)) & tu <= max(ex(j, :)));
        end
    end
    if an.exclude_saturated, m = m & ~sat; end

    offset = led_off;  origen = 'fin del LED';
    if isfield(J, 'sync') && isfield(J.sync, 'offset_auto') && ~J.sync.offset_auto
        offset = J.sync.offset_s;  origen = 'manual (FSRScope)';
    end
    if isnan(offset), offset = 0; origen = 'sin LED (0 s)'; end
    P = struct('t', tu, 'G', adc_u * K, 'mascara', m, 'sat', sat, 'paso', paso, 'K', K, ...
               'origen_K', origen_K, 'r_feedback', r_eq, 'offset', offset, 'origen', origen, ...
               'deltaT_fijo', an.deltaT_fixed_s, 'deltaT_max', an.deltaT_max_s, 'clases', an.hist_bins, ...
               'archivo', ['R_' codigo '.csv']);
end

function s = completar(s, J, campo)
    % Overwrite the defaults in s with the fields present in J.(campo)
    if ~isfield(J, campo), return; end
    c = J.(campo);
    for f = fieldnames(s)'
        if isfield(c, f{1}), s.(f{1}) = c.(f{1}); end
    end
end

function s = sufijo(nota)
    s = '';
    if ~isempty(nota), s = [' (' nota ')']; end
end
