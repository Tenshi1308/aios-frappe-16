import axios from "axios";

const HttpClient = axios.create({
  withCredentials: true,
  headers: {
    Accept: "application/json",
    "X-Requested-With": "XMLHttpRequest",
  },
});

export function setFrappeCsrfToken(token: string | null) {
  if (token) {
    HttpClient.defaults.headers.common["X-Frappe-CSRF-Token"] = token;
    return;
  }

  delete HttpClient.defaults.headers.common["X-Frappe-CSRF-Token"];
}

/**
 * "Lihat sebagai" Super Administrator: backend memakai hak Role Profile ini (spi_fintoedu/access.py),
 * sehingga tombol & aksi yang tampil sama dengan yang dimiliki role tersebut. Hanya dihormati untuk user Administrator.
 */
export function setViewAsHeader(role: string | null) {
  if (role) {
    HttpClient.defaults.headers.common["X-SPI-View-As"] = role;
    return;
  }
  delete HttpClient.defaults.headers.common["X-SPI-View-As"];
}

export default HttpClient;
