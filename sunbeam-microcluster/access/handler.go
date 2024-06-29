// Package access implements the access control logic for the extended apis
package access

import (
	"crypto/x509"
	"net/http"
	"strings"

	"github.com/canonical/lxd/lxd/response"
	"github.com/canonical/lxd/shared/logger"

	"github.com/canonical/microcluster/rest"
	"github.com/canonical/microcluster/rest/access"
	"github.com/canonical/microcluster/state"

	"github.com/canonical/snap-openstack/sunbeam-microcluster/client"
)

// AuthenticateClusterCAHandler authenticates the cluster CA for incoming requests.
// It checks if the request is trusted and verifies the client certificate against the cluster CA.
// If the request is trusted or the client certificate is successfully verified, it allows the request.
// Otherwise, it returns a forbidden response.
func AuthenticateClusterCAHandler(state *state.State, r *http.Request) response.Response {

	resp := access.AllowAuthenticated(state, r)

	// AllowAuthenticated returns EmptySyncResponse if the request is trusted.
	if resp == response.EmptySyncResponse {
		return resp
	}

	leader, err := state.Leader()

	if err != nil {
		logger.Errorf("Failed to get leader client: %v", err)
		return response.InternalError(err)
	}

	// If this takes too long, we should look into caching the cluster CA.
	clusterCA, err := client.ConfigClusterCAGet(state.Context, leader)
	if err != nil {
		// If no CA is configured, simply reject the request
		if strings.Contains(err.Error(), "not found") {
			logger.Debug("No cluster CA configured, rejecting request")
			return response.Forbidden(nil)
		}
		logger.Errorf("Failed to get cluster CA: %v", err)
		return response.InternalError(nil)
	}

	roots := x509.NewCertPool()
	ok := roots.AppendCertsFromPEM([]byte(clusterCA))
	if !ok {
		logger.Error("Failed to parse cluster CA")
		return response.InternalError(nil)
	}

	if r.TLS == nil {
		logger.Error("Rejecting request without TLS")
		return response.Forbidden(nil)
	}

	if len(r.TLS.PeerCertificates) > 10 {
		logger.Error("Rejecting request with too many certificates")
		return response.Forbidden(nil)
	}

	opts := x509.VerifyOptions{
		Roots:         roots,
		Intermediates: x509.NewCertPool(),
		KeyUsages:     []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth, x509.ExtKeyUsageServerAuth},
	}

	for _, cert := range r.TLS.PeerCertificates {
		_, err := cert.Verify(opts)
		if err == nil {
			logger.Debug("Allowing request authenticated using cluster CA")
			return response.EmptySyncResponse
		}
	}

	return response.Forbidden(nil)
}

// AuthenticateUnixHandler only allow requests coming from the unix socket.
func AuthenticateUnixHandler(_ *state.State, r *http.Request) response.Response {
	if r.RemoteAddr == "@" {
		return response.EmptySyncResponse
	}
	return response.Forbidden(nil)
}

// ClusterCATrustedEndpoint is a helper to simplify the creation of a cluster peer endpoint.
func ClusterCATrustedEndpoint(handler func(state *state.State, r *http.Request) response.Response, proxyTarget bool) rest.EndpointAction {
	return rest.EndpointAction{
		Handler:        handler,
		AccessHandler:  AuthenticateClusterCAHandler,
		AllowUntrusted: true,
		ProxyTarget:    proxyTarget,
	}
}
