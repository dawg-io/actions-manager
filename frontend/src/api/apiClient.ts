/**
 * Configured Axios instance for ActionsManager API requests.
 *
 * Sends the server-issued HttpOnly session cookie with API requests.
 */
import axios from "axios";
import config from "../config";

const apiClient = axios.create({
  baseURL: config.BACKEND_URL,
  withCredentials: true,
});

export default apiClient;
