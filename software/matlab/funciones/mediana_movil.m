function m = mediana_movil(y, k)
% MEDIANA_MOVIL  Centred moving median of K samples ignoring NaN (MATLAB and Octave).
    if ~exist('OCTAVE_VERSION', 'builtin')
        m = movmedian(y, k, 'omitnan');
        return
    end
    n = numel(y);  m = nan(size(y));               % Octave: movmedian has no 'omitnan'
    a = floor((k - 1) / 2);  b = k - 1 - a;
    for i = 1:n
        w = y(max(1, i - a):min(n, i + b));
        w = w(isfinite(w));
        if ~isempty(w), m(i) = median(w); end
    end
end
