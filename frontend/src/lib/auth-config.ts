// Configurazione accesso in fase di "early access".
// SOLO questa email può accedere alla dashboard. Chiunque altro provi a
// registrarsi o ad accedere vede il banner "non ancora pronti".
// Per aprire il tool a tutti: vedi NOTE in fondo.

export const OWNER_EMAIL = 'daniele.ritrovato@gmail.com';

/** true se l'email passata è quella dell'unico utente autorizzato. */
export function isOwnerEmail(email?: string | null): boolean {
    return !!email && email.trim().toLowerCase() === OWNER_EMAIL;
}

// Testo mostrato a chiunque non sia l'owner (registrazione o login altrui).
export const NOT_READY_TITLE = 'Non siamo ancora pronti';
export const NOT_READY_MESSAGE =
    'Ti avviseremo quando lo sapremo! Per tutte le info segui le nostre pagine social.';

// NOTE per aprire il tool al pubblico in futuro:
//  1) AuthSection.tsx: rimuovere il gate `isOwnerEmail` da login/registrazione
//     (ripristinare la vera signUp e il login per tutte le email).
//  2) ProtectedRoute.tsx: togliere il controllo `isOwnerEmail(user.email)`,
//     lasciando solo il controllo `user` presente.
//  3) Supabase Dashboard → Authentication → riattivare i signup pubblici.
