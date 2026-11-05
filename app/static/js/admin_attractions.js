/* 后台景点列表：彻底删除前的二次确认（第二道只在有订单时出现）。 */
window.confirmDeleteAttraction = function (form) {
  var data = form.dataset;
  var lines = [data.main, "", data.detail];
  if (Number(data.images || 0) > 0 && data.imagesNote) {
    lines.push(data.imagesNote);
  }
  if (!window.confirm(lines.join("\n"))) return false;

  if (Number(data.bookings || 0) > 0) {
    return window.confirm(data.last);
  }
  return true;
};
