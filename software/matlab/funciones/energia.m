function [E_tras, E_rot, unidad] = energia(D, masa_g, k_inercia, diametro_mm)
% ENERGIA  Kinetic energy of the group per frame: translation N<½v²> and rotation N<½kR²ω²>.
%   masa_g = 0: per unit mass [uJ/kg] (= mm²/s²); mass in g: [nJ].
%   k_inercia: I = k·m·R² (0.5 = uniform disc, an assumption); diametro_mm: 33 by default.
    if nargin < 2, masa_g = 0; end
    if nargin < 3, k_inercia = 0.5; end
    if nargin < 4, diametro_mm = 33; end
    R = diametro_mm / 2;
    E_tras = D.N * 0.5 * D.V2;
    E_rot = D.N * 0.5 * k_inercia * R ^ 2 * D.W2;
    unidad = 'E/m [\muJ/kg]';
    if masa_g > 0
        E_tras = E_tras * masa_g;  E_rot = E_rot * masa_g;  unidad = 'E [nJ]';
    end
end
