# Open Quantum Safe (OQS) Python Module

import os
import sys
# import ctypes to call native
import ctypes as ct
import ctypes.util as ctu
# import platform to learn the OS we're on
import platform


LIBOQS_SHARED_OBJ = 'oqs' if platform.system() == 'Windows' else 'liboqs.so'
LIBOQS_INSTALL_PATH = 'LIBOQS_INSTALL_PATH'


# expected return value from native OQS functions
_OQS_SUCCESS = 0


def _load_shared_obj():
    """Attempts to load native OQS library."""
    paths = []

    # try custom env var first
    if LIBOQS_INSTALL_PATH in os.environ:
        paths.append(os.environ[LIBOQS_INSTALL_PATH])

    # search typical locations too
    paths += [ctu.find_library('oqs'), os.path.join(os.curdir, LIBOQS_SHARED_OBJ)]
    dll = ct.windll if platform.system() == 'Windows' else ct.cdll

    for path in paths:
        if path and os.path.exists(path):
            lib = dll.LoadLibrary(path)
            return lib

    raise RuntimeError('No liboqs.so found!')


try:
    # TODO: fix global liboqs
    liboqs = _load_shared_obj()
    assert liboqs
except OSError as err:
    sys.exit('Could not load liboqs shared library')
except RuntimeError as err:
    sys.exit('No liboqs shared libraries found')


class MechanismNotSupportedError(Exception):
    """Exception raised when an algorithm is not supported by OQS.

    Attribute:
        alg_name -- the requested algorithm name
    """

    def __init__(self, alg_name):
        self.alg_name = alg_name
        self.message = alg_name + ' is not supported by OQS'

class MechanismNotEnabledError(MechanismNotSupportedError):
    """Exception raised when an algorithm is not supported but not enabled by OQS.

    Attribute:
        alg_name -- the requested algorithm name
    """

    def __init__(self, alg_name):
        self.alg_name = alg_name
        self.message = alg_name + ' is not supported but not enabled by OQS'

############################################
# KEM
############################################

# The native KEM structure returned by OQS
class OQS_KEM(ct.Structure):
    """
    An OQS key encapsulation object.
    """

    _fields_ = [
        ("method_name", ct.c_char_p),
        ("alg_version", ct.c_char_p),
        ("claimed_nist_level", ct.c_ubyte),
        ("ind_cca", ct.c_ubyte),
        ("length_public_key", ct.c_size_t),
        ("length_secret_key", ct.c_size_t),
        ("length_ciphertext", ct.c_size_t),
        ("length_shared_secret", ct.c_size_t),
        ("keypair_cb", ct.c_void_p),
        ("encaps_cb", ct.c_void_p),
        ("decaps_cb", ct.c_void_p)
    ]

    def __init__(self, alg_name, secret_key = None):
        """
        alg_name -- a KEM mechanism algorithm name. Enabled KEM mechanisms can
        be obtained with get_enabled_KEM_mechanisms()
        secret_key -- the optional secret key, if previously generated by
        generate_keypair()
        """
        self.alg_name = alg_name
        if alg_name not in _enabled_KEMs:
            # perhaps it's a supported but not enabled alg
            if alg_name in _supported_KEMs:
                raise MechanismNotEnabledError(alg_name)
            else:
                raise MechanismNotSupportedError(alg_name)

        self._kem = liboqs.OQS_KEM_new( ct.create_string_buffer(alg_name.encode()) )

        self.details = {
            'name' : self._kem.contents.method_name.decode(),
            'version' : self._kem.contents.alg_version.decode(),
            'claimed_nist_level' : int(self._kem.contents.claimed_nist_level),
            'is_ind_cca' : bool(self._kem.contents.ind_cca),
            'length_public_key' : int(self._kem.contents.length_public_key),
            'length_secret_key' : int(self._kem.contents.length_secret_key),
            'length_ciphertext' : int(self._kem.contents.length_ciphertext),
            'length_shared_secret' : int(self._kem.contents.length_shared_secret) }

        if secret_key:
            self.secret_key = ct.create_string_buffer(secret_key, self._kem.contents.length_secret_key)

    def __enter__(self):
        return self

    def __exit__(self, ctx_type, ctx_value, ctx_traceback):
        self.free()

    def generate_keypair(self):
        """Generates a new keypair and returns the public key.

        If needed, the secret key can be obtained by calling export_secret_key.
        """
        public_key = ct.create_string_buffer(self._kem.contents.length_public_key)
        self.secret_key = ct.create_string_buffer(self._kem.contents.length_secret_key)
        _rv = liboqs.OQS_KEM_keypair(self._kem, ct.byref(public_key), ct.byref(self.secret_key))
        return bytes(public_key) if _rv == _OQS_SUCCESS else 0

    def export_secret_key(self):
        """Exports the secret key."""
        return bytes(self.secret_key)

    def encap_secret(self, public_key):
        """Generates and encapsulates a secret using the provided public key.

        Attribute:
            public_key -- the peer's public key.
        """
        my_public_key = ct.create_string_buffer(public_key, self._kem.contents.length_public_key)
        ciphertext = ct.create_string_buffer(self._kem.contents.length_ciphertext)
        shared_secret = ct.create_string_buffer(self._kem.contents.length_shared_secret)
        _rv = liboqs.OQS_KEM_encaps(self._kem, ct.byref(ciphertext), ct.byref(shared_secret), my_public_key)
        return bytes(ciphertext), bytes(shared_secret) if _rv == _OQS_SUCCESS else 0

    def decap_secret(self, ciphertext):
        """Decapsulates the ciphertext and returns the secret.

        Attribute:
            ciphertext -- the ciphertext received from the peer.
        """
        my_ciphertext = ct.create_string_buffer(ciphertext, self._kem.contents.length_ciphertext)
        shared_secret = ct.create_string_buffer(self._kem.contents.length_shared_secret)
        _rv = liboqs.OQS_KEM_decaps(self._kem, ct.byref(shared_secret), my_ciphertext, self.secret_key)
        return bytes(shared_secret) if _rv == _OQS_SUCCESS else 0

    def free(self):
        """Releases the native resources."""
        liboqs.OQS_KEM_free(self._kem)

    def __repr__(self):
        return "Key encapsulation mechanism: " + self._kem.contents.method_name.decode()


liboqs.OQS_KEM_new.restype = ct.POINTER(OQS_KEM)
liboqs.OQS_KEM_alg_identifier.restype = ct.c_char_p


def is_KEM_enabled(alg_name):
    """Returns True if the KEM algorithm is enabled, False otherwise.

    Attribute:
        alg_name -- a KEM mechanism algorithm name
    """
    try:
        kem = liboqs.OQS_KEM_new(ct.create_string_buffer(alg_name.encode()))
        if(kem.contents):
            liboqs.OQS_KEM_free(kem)
            return True
    except ValueError:
        pass
    return False


_KEM_alg_ids = [liboqs.OQS_KEM_alg_identifier(i) for i in range(liboqs.OQS_KEM_alg_count())]
_supported_KEMs = [i.decode() for i in _KEM_alg_ids]
_enabled_KEMs = [i for i in _supported_KEMs if is_KEM_enabled(i)]


def get_enabled_KEM_mechanisms():
    """Returns the list of enabled KEM mechanisms."""
    return _enabled_KEMs

def print_enabled_KEM_mechanisms():
    """Prints the list of enabled KEM mechanisms."""
    print('Enabled KEM mechanisms:', ', '.join(_enabled_KEMs))


############################################
# Signatures
############################################

# The native signature structure returned by OQS
class OQS_SIG(ct.Structure):
    """An OQS signature object."""

    _fields_ = [
        ("method_name", ct.c_char_p),
        ("alg_version", ct.c_char_p),
        ("claimed_nist_level", ct.c_ubyte),
        ("euf_cma", ct.c_ubyte),
        ("length_public_key", ct.c_size_t),
        ("length_secret_key", ct.c_size_t),
        ("length_signature", ct.c_size_t),
        ("keypair_cb", ct.c_void_p),
        ("sign_cb", ct.c_void_p),
        ("verify_cb", ct.c_void_p)
    ]

    def __init__(self, alg_name, secret_key = None):
        """
        Attributes:
        alg_name -- a signature mechanism algorithm name. Enabled signature mechanisms can be obtained with get_enabled_KEM_mechanisms
        secret_key -- the optional secret key, if previously generated by generate_keypair
        """
        if alg_name not in _enabled_sigs:
            # perhaps it's a supported but not enabled alg
            if alg_name in _supported_sigs:
                raise MechanismNotEnabledError(alg_name)
            else:
                raise MechanismNotSupportedError(alg_name)

        self._sig = liboqs.OQS_SIG_new( ct.create_string_buffer(alg_name.encode()) )
        self.details = {
            'name' : self._sig.contents.method_name.decode(),
            'version' : self._sig.contents.alg_version.decode(),
            'claimed_nist_level' : int(self._sig.contents.claimed_nist_level),
            'is_euf_cma' : bool(self._sig.contents.euf_cma),
            'length_public_key' : int(self._sig.contents.length_public_key),
            'length_secret_key' : int(self._sig.contents.length_secret_key),
            'length_signature' : int(self._sig.contents.length_signature) }
        if secret_key:
            self.secret_key = ct.create_string_buffer(secret_key, self._sig.contents.length_secret_key)

    def __enter__(self):
        return self

    def __exit__(self, ctx_type, ctx_value, ctx_traceback):
        self.free()

    def generate_keypair(self):
        """Generates a new keypair and returns the public key.

        If needed, the secret key can be obtained by calling export_secret_key.
        """
        public_key = ct.create_string_buffer(self._sig.contents.length_public_key)
        self.secret_key = ct.create_string_buffer(self._sig.contents.length_secret_key)
        _rv = liboqs.OQS_SIG_keypair(self._sig, ct.byref(public_key), ct.byref(self.secret_key))
        return bytes(public_key) if _rv == _OQS_SUCCESS else 0

    def export_secret_key(self):
        """Exports the secret key."""
        return bytes(self.secret_key)

    def sign(self, message):
        """Signs the provided message and returns the signature.

        Attribute:
            message -- the message to sign.
        """
        my_message = ct.create_string_buffer(message, len(message)) # provide length to avoid extra null char
        message_len = ct.c_int(len(my_message))
        signature = ct.create_string_buffer(self._sig.contents.length_signature)
        sig_len = ct.c_int(0)
        _rv = liboqs.OQS_SIG_sign(self._sig, ct.byref(signature), ct.byref(sig_len), my_message, message_len, self.secret_key)
        return bytes(signature[:sig_len.value]) if _rv == _OQS_SUCCESS else 0

    def verify(self, message, signature, public_key):
        """Verifies the provided signature on the message; returns True if valid.

        Attributes:
            message -- the signed message.
            signature -- the signature on the message.
            public_key -- the signer's publid key.
        """
        my_message = ct.create_string_buffer(message, len(message)) # provide length to avoid extra null char
        message_len = ct.c_int(len(my_message))
        my_signature = ct.create_string_buffer(signature, len(signature)) # provide length to avoid extra null char
        sig_len = ct.c_int(len(my_signature))
        my_public_key = ct.create_string_buffer(public_key, self._sig.contents.length_public_key)
        _rv = liboqs.OQS_SIG_verify(self._sig, my_message, message_len, my_signature, sig_len, my_public_key)
        return True if _rv == _OQS_SUCCESS else False

    def free(self):
        """Releases the native resources."""
        liboqs.OQS_SIG_free(self._sig)

    def __repr__(self):
        return "Signature mechanism: " + self._sig.contents.method_name.decode()


liboqs.OQS_SIG_new.restype = ct.POINTER(OQS_SIG)
liboqs.OQS_SIG_alg_identifier.restype = ct.c_char_p


def is_sig_enabled(alg_name):
    """Returns True if the signature algorithm is enabled, False otherwise.

    Attribute:
        alg_name -- a signature mechanism algorithm name
    """
    try:
        sig = liboqs.OQS_SIG_new(ct.create_string_buffer(alg_name.encode()))
        if(sig.contents):
            liboqs.OQS_SIG_free(sig)
            return True
    except ValueError:
        pass
    return False


_sig_alg_ids = [liboqs.OQS_SIG_alg_identifier(i) for i in range(liboqs.OQS_SIG_alg_count())]
_supported_sigs = [i.decode() for i in _sig_alg_ids]
_enabled_sigs = [i for i in _supported_sigs if is_sig_enabled(i)]


def get_enabled_sig_mechanisms():
    """Returns the list of enabled signature mechanisms."""
    return _enabled_sigs


def print_enabled_sig_mechanisms():
    """Prints the list of enabled signature mechanisms."""
    print('Enabled signature mechanisms:', ', '.join(_enabled_sigs))
