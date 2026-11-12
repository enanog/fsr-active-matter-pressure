function v = rapidez_conjunto(D, estadistico)
% RAPIDEZ_CONJUNTO  One speed per frame from the robots' speeds [mm/s]:
%   'media' (= D.V, default), 'mediana', 'p90' (90th percentile, the report's mobility index), 'p10'
    if nargin < 2, estadistico = 'media'; end
    switch lower(estadistico)
        case 'media',   v = D.V;
        case 'mediana', v = percentil(D.S, 50, 2);
        case 'p90',     v = percentil(D.S, 90, 2);
        case 'p10',     v = percentil(D.S, 10, 2);
        otherwise, error('estadistico = media | mediana | p90 | p10');
    end
end
