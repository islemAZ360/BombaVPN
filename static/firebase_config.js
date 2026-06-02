import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import { getAuth, signInWithPopup, GoogleAuthProvider, onAuthStateChanged, signOut } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js";

const firebaseConfig = {
  apiKey: "AIzaSyB2JorEdtoQACpLYU4dzfOsESyX-A4BK3A",
  authDomain: "vpnbomba-d87e0.firebaseapp.com",
  projectId: "vpnbomba-d87e0",
  storageBucket: "vpnbomba-d87e0.firebasestorage.app",
  messagingSenderId: "741022847290",
  appId: "1:741022847290:web:df593562f5ec77185dc003",
  measurementId: "G-PQT4MHSV8Y"
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const googleProvider = new GoogleAuthProvider();

export { auth, signInWithPopup, googleProvider, onAuthStateChanged, signOut };
