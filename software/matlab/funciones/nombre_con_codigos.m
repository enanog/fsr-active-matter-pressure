function nombre = nombre_con_codigos(nombre, codigos)
% NOMBRE_CON_CODIGOS  File name + the measurement codes it shows:
%   'velocidad_tiempo' + {'20261030_1100_22AH_60', '20261106_1600_22AH_60'}
%   -> 'velocidad_tiempo__20261030_1100_22AH_60-20261106_1600_22AH_60'
% Codes already in the name are not repeated. With too many codes for a Windows path (> 110 characters,
% about 5 trials) -> 'velocidad_tiempo__8ensayos_20260924_1600_22AH_60_a_20261106_1600_22AH_60'.
    codigos = codigos(cellfun(@isempty, strfind(nombre, codigos)));
    if isempty(codigos), return; end
    sufijo = strjoin(codigos, '-');
    if numel(sufijo) > 110
        sufijo = sprintf('%densayos_%s_a_%s', numel(codigos), codigos{1}, codigos{end});
    end
    nombre = [nombre '__' sufijo];
end
