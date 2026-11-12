function G = presion_valida(P)
% PRESION_VALIDA  G [uS] with NaN outside the FSRScope analysis mask (crop, exclusions, saturation).
    G = P.G;
    G(~P.mascara) = NaN;
end
