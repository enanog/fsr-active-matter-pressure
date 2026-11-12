function x = muestras_velocidad(D, fuente, suav_s)
% MUESTRAS_VELOCIDAD  Samples for histograms and distributions [mm/s].
%   fuente = 'media'      V of the group per frame (one sample per frame)
%            'individual' |v| of every observed robot and frame
%   suav_s > 0 only for 'media': distribution of the smoothed V (changes width and tails)
    if nargin < 3, suav_s = 0; end
    switch lower(fuente)
        case 'media'
            x = suavizar(D.t, D.V, suav_s);
        case 'individual'
            x = D.v_ind;
        otherwise
            error('fuente = ''media'' o ''individual''');
    end
    x = x(isfinite(x));
end
