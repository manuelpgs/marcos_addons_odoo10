# marcos_addons_odoo10
Somes enhancing to original's marcos_addons for ODOO 10 version

Please check the commits or contact with me for clarifications.

--------------------------------------------------------------------

En resumén los cambios son:

- Permitir que los diarios de compra del tipo "normal" puedan generar retenciones de ITBIS e ISR en el 606.  Esto así debido a que en algunos casos tenemos proveedores que nos dan un NCF usando su cédula como RNC y en estos casos siempre que sea posible el DGII nos manda a retenerles el ITBIS e ISR.
- Corrige un problema en el reporte 607 que se sucitaba al generar facturas de ventas donde por error no se escogía un producto.
- Corrige un problema relacionado con pagos tardios de facturas de proveedores informales, si la factura es de enero pero la pagamos en febrero, en el reporte del 606 de febrero salía esta factura nuevamente sin importar que no tuviera retenciones.
- Corrige un problema relacionado al caso anterior, si la factura del proveedor informal con fecha de enero es pagada en febrero y efectivamente le hicimos retenciones, al volver a generar (por x razón) el reporte del 606 de enero, esta factura viene con las retenciones que se hicieron en febrero al pagarla y solo deberían salir en el 606 de febrero. 
