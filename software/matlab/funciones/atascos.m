function A = atascos(D, umbral, suav_s, min_s)
% ATASCOS  Jam spans: moving median (SUAV_S s) of V below UMBRAL [mm/s] for at least MIN_S s
% (same criterion as the Velocidades app: 0.35 mm/s, 30 s, 20 s).
%   A.mascara (per frame), A.tramos [start end] in video s, A.fraccion, A.n, A.dur_max [s]
    if nargin < 2, umbral = 0.35; end
    if nargin < 3, suav_s = 30; end
    if nargin < 4, min_s = 20; end
    t = D.t;
    dt = median(diff(t));
    s = mediana_movil(D.V, max(1, round(suav_s / dt)));
    abajo = s(:) < umbral;
    d = diff([false; abajo; false]);
    ini = find(d == 1);  fin = find(d == -1) - 1;
    dur = t(fin) - t(ini) + dt;
    ok = dur >= min_s;
    A.mascara = false(size(abajo));
    for j = find(ok)'
        A.mascara(ini(j):fin(j)) = true;
    end
    A.tramos = [t(ini(ok)), t(fin(ok)) + dt];
    A.fraccion = mean(A.mascara);
    A.n = nnz(ok);
    A.dur_max = max([dur(ok); 0]);
end
