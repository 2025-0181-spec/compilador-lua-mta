-- Ejemplo de script SERVER-SIDE para probar el compilador.
-- Copialo a la carpeta input/ y compilalo desde el menu.
addEventHandler("onResourceStart", resourceRoot, function()
    outputServerLog("Recurso de prueba iniciado correctamente")
end)

addCommandHandler("hola", function(player)
    outputChatBox("Hola desde un script protegido!", player, 0, 255, 0)
end)
