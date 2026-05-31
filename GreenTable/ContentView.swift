import SwiftUI

struct ContentView: View {
    @EnvironmentObject var authStore: AuthStore

    var body: some View {
        if authStore.isAuthenticated {
            TabView {
                DashboardView()
                    .tabItem {
                        Label("Dashboard", systemImage: "house")
                    }

                FriendsView()
                    .tabItem {
                        Label("Friends", systemImage: "person.2")
                    }

                CreateSessionView()
                    .tabItem {
                        Label("Create", systemImage: "plus.circle")
                    }
            }
        } else {
            AuthView()
        }
    }
}

#Preview {
    ContentView()
        .environmentObject(AuthStore())
}
